#include "bridgeserver.h"
#include "version.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonObject>
#include <QtCore/QRandomGenerator>
#include <QtCore/QRegularExpression>
#include <QtCore/QSaveFile>
#include <QtCore/QTimer>
#include <QtCore/QVariantList>
#include <QtNetwork/QHostAddress>
#include <QtNetwork/QTcpSocket>
#include <QtQml/QJSValue>
#include <QtWidgets/QAbstractButton>
#include <QtWidgets/QApplication>
#include <QtWidgets/QCheckBox>
#include <QtWidgets/QDialog>
#include <QtWidgets/QLabel>
#include <QtWidgets/QMessageBox>
#include <QtWidgets/QProgressBar>
#include <QtWidgets/QProgressDialog>
#include <QtWidgets/QRadioButton>
#include <QtWidgets/QWidget>

#include <dzapp.h>
#include <dzscript.h>

namespace {

const int kMaxHeaderBytes = 64 * 1024;
const int kMaxBodyBytes = 64 * 1024 * 1024;

QByteArray statusText(int status)
{
	switch (status) {
	case 200: return "OK";
	case 400: return "Bad Request";
	case 401: return "Unauthorized";
	case 403: return "Forbidden";
	case 404: return "Not Found";
	case 405: return "Method Not Allowed";
	case 409: return "Conflict";
	case 413: return "Payload Too Large";
	default: return "Internal Server Error";
	}
}

QByteArray errorJson(const QString &code, const QString &message)
{
	QJsonObject err;
	err.insert(QStringLiteral("code"), code);
	err.insert(QStringLiteral("message"), message);
	QJsonObject obj;
	obj.insert(QStringLiteral("ok"), false);
	obj.insert(QStringLiteral("error"), err);
	return QJsonDocument(obj).toJson(QJsonDocument::Compact);
}

// Compares in constant time so the token cannot be guessed byte by byte.
bool constantTimeEquals(const QByteArray &a, const QByteArray &b)
{
	if (a.size() != b.size()) {
		return false;
	}
	unsigned char diff = 0;
	for (int i = 0; i < a.size(); ++i) {
		diff |= static_cast<unsigned char>(a.at(i) ^ b.at(i));
	}
	return diff == 0;
}

void restrictToOwner(const QString &path)
{
	QFile::setPermissions(path, QFileDevice::ReadOwner | QFileDevice::WriteOwner);
}

// ------------------------------------------------------------- dialogs --
// A modal dialog runs its own event loop, so the bridge keeps answering HTTP
// requests (and its timer keeps firing) while a script waits on one.

QString plainText(const QString &html)
{
	QString t = html;
	static const QRegularExpression br(QStringLiteral("<br\\s*/?>"), QRegularExpression::CaseInsensitiveOption);
	static const QRegularExpression tags(QStringLiteral("<[^>]*>"));
	t.replace(br, QStringLiteral("\n"));
	t.remove(tags);
	t.replace(QStringLiteral("&nbsp;"), QStringLiteral(" "));
	t.replace(QStringLiteral("&lt;"), QStringLiteral("<"));
	t.replace(QStringLiteral("&gt;"), QStringLiteral(">"));
	t.replace(QStringLiteral("&quot;"), QStringLiteral("\""));
	t.replace(QStringLiteral("&amp;"), QStringLiteral("&"));
	return t.trimmed();
}

QString buttonText(const QAbstractButton *b)
{
	QString t = b->text();
	t.remove(QLatin1Char('&'));
	return t.trimmed();
}

QString dialogId(const QWidget *w)
{
	return QString::number(reinterpret_cast<quintptr>(w), 16);
}

bool isOption(const QAbstractButton *b)
{
	return qobject_cast<const QCheckBox *>(b) || qobject_cast<const QRadioButton *>(b);
}

// Progress windows are modal too, but nobody needs to answer them.
bool isProgress(QWidget *w)
{
	return qobject_cast<QProgressDialog *>(w) || !w->findChildren<QProgressBar *>().isEmpty();
}

// Visible modal windows, the active one first.
QList<QWidget *> openDialogs()
{
	QList<QWidget *> out;
	QWidget *active = QApplication::activeModalWidget();
	if (active && active->isVisible()) {
		out << active;
	}
	const QList<QWidget *> tops = QApplication::topLevelWidgets();
	for (QWidget *w : tops) {
		if (w != active && w->isVisible() && w->isModal()) {
			out << w;
		}
	}
	return out;
}

QJsonObject describeDialog(QWidget *w)
{
	QJsonObject o;
	o.insert(QStringLiteral("id"), dialogId(w));
	o.insert(QStringLiteral("title"), w->windowTitle());
	o.insert(QStringLiteral("class"), QString::fromLatin1(w->metaObject()->className()));
	if (isProgress(w)) {
		o.insert(QStringLiteral("progress"), true);
	}

	QStringList texts;
	if (QMessageBox *box = qobject_cast<QMessageBox *>(w)) {
		texts << plainText(box->text());
		if (!box->informativeText().isEmpty()) {
			texts << plainText(box->informativeText());
		}
	} else {
		const QList<QLabel *> labels = w->findChildren<QLabel *>();
		for (QLabel *label : labels) {
			const QString t = plainText(label->text());
			if (!t.isEmpty() && label->isVisibleTo(w)) {
				texts << t;
			}
		}
	}
	QString text = texts.join(QLatin1Char('\n'));
	if (text.size() > 4000) {
		text = text.left(4000) + QStringLiteral("...");
	}
	o.insert(QStringLiteral("text"), text);

	QJsonArray buttons;
	QJsonArray options;
	const QList<QAbstractButton *> all = w->findChildren<QAbstractButton *>();
	for (QAbstractButton *b : all) {
		const QString t = buttonText(b);
		if (t.isEmpty() || !b->isVisibleTo(w)) {
			continue;
		}
		if (isOption(b)) {
			QJsonObject opt;
			opt.insert(QStringLiteral("label"), t);
			opt.insert(QStringLiteral("kind"), qobject_cast<QCheckBox *>(b) ? QStringLiteral("checkbox") : QStringLiteral("radio"));
			opt.insert(QStringLiteral("checked"), b->isChecked());
			if (!b->isEnabled()) {
				opt.insert(QStringLiteral("enabled"), false);
			}
			options.append(opt);
		} else if (b->isEnabled()) {
			buttons.append(t);
		}
	}
	o.insert(QStringLiteral("buttons"), buttons);
	if (!options.isEmpty()) {
		o.insert(QStringLiteral("options"), options);
	}
	return o;
}

// Exact label first (case and "&" ignored), then the only label that starts with it.
QAbstractButton *findButton(QWidget *w, const QString &name, bool option)
{
	const QString want = QString(name).remove(QLatin1Char('&')).trimmed();
	QAbstractButton *prefix = nullptr;
	int prefixCount = 0;
	const QList<QAbstractButton *> all = w->findChildren<QAbstractButton *>();
	for (QAbstractButton *b : all) {
		if (isOption(b) != option || !b->isVisibleTo(w) || !b->isEnabled()) {
			continue;
		}
		const QString t = buttonText(b);
		if (t.compare(want, Qt::CaseInsensitive) == 0) {
			return b;
		}
		if (!want.isEmpty() && t.startsWith(want, Qt::CaseInsensitive)) {
			prefix = b;
			++prefixCount;
		}
	}
	return prefixCount == 1 ? prefix : nullptr;
}

// Sets check boxes and radio buttons by label. Returns the labels not found.
QStringList setOptions(QWidget *w, const QJsonArray &check, const QJsonArray &uncheck)
{
	QStringList missing;
	for (int pass = 0; pass < 2; ++pass) {
		const QJsonArray &list = pass == 0 ? check : uncheck;
		for (const QJsonValue &v : list) {
			QAbstractButton *b = findButton(w, v.toString(), true);
			if (!b) {
				missing << v.toString();
				continue;
			}
			if (b->isChecked() != (pass == 0)) {
				b->click(); // the same signals as a user's click
			}
		}
	}
	return missing;
}

// Presses a button after the HTTP answer is sent: the click ends the dialog's
// event loop and the waiting script carries on.
bool pressButton(QWidget *w, const QString &name, QString &pressed)
{
	QAbstractButton *b = findButton(w, name, false);
	if (b) {
		pressed = buttonText(b);
		QMetaObject::invokeMethod(b, "click", Qt::QueuedConnection);
		return true;
	}
	const QString lower = name.trimmed().toLower();
	if (lower == QLatin1String("escape") || lower == QLatin1String("close")) {
		pressed = QStringLiteral("escape");
		if (qobject_cast<QDialog *>(w)) {
			QMetaObject::invokeMethod(w, "reject", Qt::QueuedConnection);
		} else {
			QMetaObject::invokeMethod(w, "close", Qt::QueuedConnection);
		}
		return true;
	}
	return false;
}

QByteArray okJson(const QJsonValue &result)
{
	QJsonObject obj;
	obj.insert(QStringLiteral("ok"), true);
	obj.insert(QStringLiteral("result"), result);
	return QJsonDocument(obj).toJson(QJsonDocument::Compact);
}

} // namespace

DazMcpBridgeServer::DazMcpBridgeServer(QObject *parent)
	: QObject(parent), m_server(new QTcpServer(this)), m_busy(false), m_dialogTimer(new QTimer(this))
{
	connect(m_server, &QTcpServer::newConnection, this, &DazMcpBridgeServer::onNewConnection);
	m_dialogTimer->setInterval(250);
	connect(m_dialogTimer, &QTimer::timeout, this, &DazMcpBridgeServer::scanDialogs);
}

DazMcpBridgeServer::~DazMcpBridgeServer()
{
	stop();
}

QString DazMcpBridgeServer::configDir()
{
	const QByteArray overrideDir = qgetenv("DAZ3D_MCP_HOME");
	if (!overrideDir.isEmpty()) {
		return QString::fromLocal8Bit(overrideDir);
	}
	return QDir::homePath() + QStringLiteral("/.daz3d-mcp");
}

bool DazMcpBridgeServer::start()
{
	if (m_server->isListening()) {
		return true;
	}
	if (!loadOrCreateToken()) {
		return false;
	}

	quint16 basePort = DAZMCP_DEFAULT_PORT;
	bool ok = false;
	const int envPort = qEnvironmentVariableIntValue("DAZ3D_MCP_PORT", &ok);
	if (ok && envPort > 0 && envPort < 65536) {
		basePort = static_cast<quint16>(envPort);
	}

	// Try a few ports so two Daz instances can run side by side.
	for (quint16 p = basePort; p < basePort + 10; ++p) {
		if (m_server->listen(QHostAddress::LocalHost, p)) {
			if (!writeDiscoveryFile()) {
				m_server->close();
				return false;
			}
			return true;
		}
	}
	m_lastError = QStringLiteral("Could not listen on 127.0.0.1 ports %1-%2: %3")
		.arg(basePort).arg(basePort + 9).arg(m_server->errorString());
	return false;
}

void DazMcpBridgeServer::stop()
{
	if (m_server->isListening()) {
		m_server->close();
		removeDiscoveryFile();
	}
}

bool DazMcpBridgeServer::isRunning() const
{
	return m_server->isListening();
}

quint16 DazMcpBridgeServer::port() const
{
	return m_server->serverPort();
}

QString DazMcpBridgeServer::lastError() const
{
	return m_lastError;
}

bool DazMcpBridgeServer::loadOrCreateToken()
{
	QDir dir(configDir());
	if (!dir.exists() && !dir.mkpath(QStringLiteral("."))) {
		m_lastError = QStringLiteral("Could not create %1").arg(dir.path());
		return false;
	}

	const QString tokenPath = dir.filePath(QStringLiteral("token"));
	QFile file(tokenPath);
	if (file.exists() && file.open(QIODevice::ReadOnly)) {
		m_token = file.readAll().trimmed();
		file.close();
		if (m_token.size() >= 32) {
			return true;
		}
	}

	// 32 random bytes from the OS generator, written as hex.
	QByteArray raw(32, Qt::Uninitialized);
	QRandomGenerator *rng = QRandomGenerator::system();
	for (int i = 0; i < raw.size(); ++i) {
		raw[i] = static_cast<char>(rng->bounded(256));
	}
	m_token = raw.toHex();

	QSaveFile out(tokenPath);
	if (!out.open(QIODevice::WriteOnly) || out.write(m_token) != m_token.size() || !out.commit()) {
		m_lastError = QStringLiteral("Could not write %1").arg(tokenPath);
		return false;
	}
	restrictToOwner(tokenPath);
	return true;
}

bool DazMcpBridgeServer::writeDiscoveryFile() const
{
	QJsonObject obj;
	obj.insert(QStringLiteral("port"), static_cast<int>(m_server->serverPort()));
	obj.insert(QStringLiteral("protocol"), DAZMCP_PROTOCOL_VERSION);
	obj.insert(QStringLiteral("bridge_version"), QStringLiteral(DAZMCP_BRIDGE_VERSION_STRING));
	obj.insert(QStringLiteral("daz_version"), dzApp ? dzApp->getLongVersionString() : QString());
	obj.insert(QStringLiteral("pid"), static_cast<qint64>(QCoreApplication::applicationPid()));

	const QString path = QDir(configDir()).filePath(QStringLiteral("bridge.json"));
	QSaveFile out(path);
	if (!out.open(QIODevice::WriteOnly)) {
		return false;
	}
	out.write(QJsonDocument(obj).toJson(QJsonDocument::Indented));
	if (!out.commit()) {
		return false;
	}
	restrictToOwner(path);
	return true;
}

void DazMcpBridgeServer::removeDiscoveryFile() const
{
	const QString path = QDir(configDir()).filePath(QStringLiteral("bridge.json"));
	QFile file(path);
	if (!file.open(QIODevice::ReadOnly)) {
		return;
	}
	const QJsonObject obj = QJsonDocument::fromJson(file.readAll()).object();
	file.close();
	// Only remove it if it still points at this process.
	if (obj.value(QStringLiteral("pid")).toVariant().toLongLong() == QCoreApplication::applicationPid()) {
		QFile::remove(path);
	}
}

void DazMcpBridgeServer::onNewConnection()
{
	while (QTcpSocket *socket = m_server->nextPendingConnection()) {
		m_buffers.insert(socket, QByteArray());
		connect(socket, &QTcpSocket::readyRead, this, &DazMcpBridgeServer::onReadyRead);
		connect(socket, &QTcpSocket::disconnected, this, &DazMcpBridgeServer::onDisconnected);
	}
}

void DazMcpBridgeServer::onDisconnected()
{
	QTcpSocket *socket = qobject_cast<QTcpSocket *>(sender());
	if (!socket) {
		return;
	}
	m_buffers.remove(socket);
	socket->deleteLater();
}

void DazMcpBridgeServer::onReadyRead()
{
	QTcpSocket *socket = qobject_cast<QTcpSocket *>(sender());
	if (!socket || !m_buffers.contains(socket)) {
		return;
	}
	QByteArray &buffer = m_buffers[socket];
	buffer.append(socket->readAll());

	Request req;
	int errorStatus = 0;
	if (!tryParse(buffer, req, errorStatus)) {
		if (errorStatus) {
			respond(socket, errorStatus, errorJson(QStringLiteral("bad_request"),
				QStringLiteral("Malformed or oversized request.")));
		}
		return; // wait for more data
	}
	// One request per connection keeps the server simple.
	disconnect(socket, &QTcpSocket::readyRead, this, &DazMcpBridgeServer::onReadyRead);
	handle(socket, req);
}

bool DazMcpBridgeServer::tryParse(QByteArray &buffer, Request &req, int &errorStatus) const
{
	errorStatus = 0;
	const int headerEnd = buffer.indexOf("\r\n\r\n");
	if (headerEnd < 0) {
		if (buffer.size() > kMaxHeaderBytes) {
			errorStatus = 413;
		}
		return false;
	}

	const QList<QByteArray> lines = buffer.left(headerEnd).split('\n');
	const QList<QByteArray> requestLine = lines.value(0).trimmed().split(' ');
	if (requestLine.size() < 2) {
		errorStatus = 400;
		return false;
	}
	req.method = QString::fromLatin1(requestLine.at(0)).toUpper();
	req.path = QString::fromLatin1(requestLine.at(1));
	for (int i = 1; i < lines.size(); ++i) {
		const QByteArray line = lines.at(i).trimmed();
		const int colon = line.indexOf(':');
		if (colon > 0) {
			req.headers.insert(QString::fromLatin1(line.left(colon)).trimmed().toLower(),
				QString::fromLatin1(line.mid(colon + 1)).trimmed());
		}
	}

	bool ok = true;
	const int contentLength = req.headers.value(QStringLiteral("content-length"), QStringLiteral("0")).toInt(&ok);
	if (!ok || contentLength < 0 || contentLength > kMaxBodyBytes) {
		errorStatus = ok ? 413 : 400;
		return false;
	}
	const int bodyStart = headerEnd + 4;
	if (buffer.size() - bodyStart < contentLength) {
		return false; // body not complete yet
	}
	req.body = buffer.mid(bodyStart, contentLength);
	buffer.clear();
	return true;
}

bool DazMcpBridgeServer::isLocalHost(const Request &req) const
{
	// Blocks DNS-rebinding: a web page cannot make the browser send a Host
	// header for 127.0.0.1 from another site name.
	const QString host = req.headers.value(QStringLiteral("host")).section(':', 0, 0).toLower();
	return host == QLatin1String("127.0.0.1") || host == QLatin1String("localhost");
}

bool DazMcpBridgeServer::isAuthorized(const Request &req) const
{
	const QString auth = req.headers.value(QStringLiteral("authorization"));
	if (!auth.startsWith(QLatin1String("Bearer "), Qt::CaseInsensitive)) {
		return false;
	}
	return constantTimeEquals(auth.mid(7).trimmed().toLatin1(), m_token);
}

void DazMcpBridgeServer::handle(QTcpSocket *socket, const Request &req)
{
	if (!isLocalHost(req) || req.headers.contains(QStringLiteral("origin"))) {
		respond(socket, 403, errorJson(QStringLiteral("forbidden"),
			QStringLiteral("Only local, non-browser clients may use the bridge.")));
		return;
	}
	if (!isAuthorized(req)) {
		respond(socket, 401, errorJson(QStringLiteral("unauthorized"),
			QStringLiteral("Missing or wrong token. Run `daz3d-mcp doctor`.")));
		return;
	}

	if (req.path == QLatin1String("/v1/status")) {
		QJsonObject obj;
		obj.insert(QStringLiteral("ok"), true);
		obj.insert(QStringLiteral("protocol"), DAZMCP_PROTOCOL_VERSION);
		obj.insert(QStringLiteral("bridge_version"), QStringLiteral(DAZMCP_BRIDGE_VERSION_STRING));
		obj.insert(QStringLiteral("daz_version"), dzApp ? dzApp->getLongVersionString() : QString());
		obj.insert(QStringLiteral("busy"), m_busy);
		obj.insert(QStringLiteral("features"), QJsonArray { QStringLiteral("dialogs") });
		respond(socket, 200, QJsonDocument(obj).toJson(QJsonDocument::Compact));
		return;
	}

	if (req.path == QLatin1String("/v1/dialogs")) {
		respond(socket, 200, listDialogs());
		return;
	}

	if (req.path == QLatin1String("/v1/dialogs/answer")) {
		if (req.method != QLatin1String("POST")) {
			respond(socket, 405, errorJson(QStringLiteral("method"), QStringLiteral("Use POST.")));
			return;
		}
		int status = 200;
		const QByteArray body = answerDialog(req.body, status);
		respond(socket, status, body);
		return;
	}

	if (req.path == QLatin1String("/v1/execute")) {
		if (req.method != QLatin1String("POST")) {
			respond(socket, 405, errorJson(QStringLiteral("method"), QStringLiteral("Use POST.")));
			return;
		}
		int status = 200;
		const QByteArray body = execute(req.body, status);
		respond(socket, status, body);
		return;
	}

	respond(socket, 404, errorJson(QStringLiteral("not_found"), QStringLiteral("Unknown path.")));
}

QByteArray DazMcpBridgeServer::execute(const QByteArray &body, int &status)
{
	if (m_busy) {
		// A script that spins the event loop could let a second request in.
		status = 409;
		return errorJson(QStringLiteral("busy"), QStringLiteral("Daz Studio is still running the previous request."));
	}

	QJsonParseError parseError;
	const QJsonObject req = QJsonDocument::fromJson(body, &parseError).object();
	if (parseError.error != QJsonParseError::NoError) {
		status = 400;
		return errorJson(QStringLiteral("bad_request"), parseError.errorString());
	}
	const QString code = req.value(QStringLiteral("code")).toString();
	const QString entry = req.value(QStringLiteral("entry")).toString(QStringLiteral("dazmcp_entry"));
	const QString args = req.value(QStringLiteral("args")).toString(QStringLiteral("{}"));
	if (code.isEmpty()) {
		status = 400;
		return errorJson(QStringLiteral("bad_request"), QStringLiteral("Field `code` is required."));
	}
	static const QRegularExpression identifier(QStringLiteral("^[A-Za-z_$][A-Za-z0-9_$]*$"));
	if (!identifier.match(entry).hasMatch()) {
		status = 400;
		return errorJson(QStringLiteral("bad_request"), QStringLiteral("Field `entry` must be a function name."));
	}

	m_busy = true;
	m_dialogRules = req.value(QStringLiteral("dialogs")).toArray();
	m_dialogLog = QJsonArray();
	m_seenDialogs.clear();
	// Dialogs already open belong to the user: never answer them by rule.
	for (QWidget *w : openDialogs()) {
		m_seenDialogs << QPointer<QWidget>(w);
	}
	m_dialogTimer->start();
	// DzScript is reference counted (its destructor is protected).
	DzScript *scriptObj = new DzScript();
	scriptObj->ref();
	DzScript &script = *scriptObj;
	// The Daz Studio 6 SDK declares DzScript::call() but dzcore does not export
	// it, so run the program with execute() and end it with the entry call.
	// Checked on Daz Studio 6.26: result() is the value of a top-level
	// `return` (the value of a last bare expression is lost), and
	// getArguments() holds the execute() arguments.
	script.setCode(code + QStringLiteral("\n;return %1(getArguments()[0]);\n").arg(entry));
	const bool ok = script.execute(QVariantList() << args);
	QByteArray out;
	if (!ok) {
		QJsonObject err;
		err.insert(QStringLiteral("code"), QStringLiteral("script_error"));
		err.insert(QStringLiteral("message"), script.errorMessage());
		err.insert(QStringLiteral("line"), script.errorLine());
		QJsonObject obj;
		obj.insert(QStringLiteral("ok"), false);
		obj.insert(QStringLiteral("error"), err);
		out = QJsonDocument(obj).toJson(QJsonDocument::Compact);
	} else {
		// The DazScript entry point already returns a JSON string.
		out = script.result().toString().toUtf8();
		if (out.isEmpty()) {
			out = "{\"ok\":true,\"result\":null}";
		}
	}
	scriptObj->unref();
	m_dialogTimer->stop();
	if (!m_dialogLog.isEmpty()) {
		QJsonObject obj = QJsonDocument::fromJson(out).object();
		if (!obj.isEmpty()) {
			obj.insert(QStringLiteral("dialogs"), m_dialogLog);
			out = QJsonDocument(obj).toJson(QJsonDocument::Compact);
		}
	}
	m_dialogRules = QJsonArray();
	m_busy = false;
	status = 200;
	return out;
}

void DazMcpBridgeServer::scanDialogs()
{
	if (!m_busy) {
		return;
	}
	const QList<QWidget *> open = openDialogs();
	for (QWidget *w : open) {
		bool seen = false;
		for (const QPointer<QWidget> &p : m_seenDialogs) {
			if (p.data() == w) {
				seen = true;
				break;
			}
		}
		if (seen || isProgress(w)) {
			continue;
		}
		m_seenDialogs << QPointer<QWidget>(w);
		QJsonObject desc = describeDialog(w);
		const QString haystack = desc.value(QStringLiteral("title")).toString() + QLatin1Char('\n') +
			desc.value(QStringLiteral("text")).toString();
		for (const QJsonValue &v : m_dialogRules) {
			const QJsonObject rule = v.toObject();
			const QRegularExpression re(rule.value(QStringLiteral("match")).toString(),
				QRegularExpression::CaseInsensitiveOption);
			if (!re.isValid() || !re.match(haystack).hasMatch()) {
				continue;
			}
			setOptions(w, rule.value(QStringLiteral("check")).toArray(), rule.value(QStringLiteral("uncheck")).toArray());
			QString pressed;
			if (pressButton(w, rule.value(QStringLiteral("button")).toString(), pressed)) {
				desc.insert(QStringLiteral("answered"), pressed);
				desc.insert(QStringLiteral("answered_by"), QStringLiteral("rule"));
			}
			break;
		}
		m_dialogLog.append(desc);
	}
}

QByteArray DazMcpBridgeServer::listDialogs() const
{
	QJsonArray dialogs;
	for (QWidget *w : openDialogs()) {
		dialogs.append(describeDialog(w));
	}
	QJsonObject result;
	result.insert(QStringLiteral("busy"), m_busy);
	result.insert(QStringLiteral("dialogs"), dialogs);
	result.insert(QStringLiteral("seen"), m_dialogLog);
	return okJson(result);
}

QByteArray DazMcpBridgeServer::answerDialog(const QByteArray &body, int &status)
{
	QJsonParseError parseError;
	const QJsonObject req = QJsonDocument::fromJson(body, &parseError).object();
	if (parseError.error != QJsonParseError::NoError) {
		status = 400;
		return errorJson(QStringLiteral("bad_request"), parseError.errorString());
	}
	const QString id = req.value(QStringLiteral("id")).toString();
	const QString button = req.value(QStringLiteral("button")).toString();
	const QJsonArray check = req.value(QStringLiteral("check")).toArray();
	const QJsonArray uncheck = req.value(QStringLiteral("uncheck")).toArray();

	QWidget *target = nullptr;
	for (QWidget *w : openDialogs()) {
		if (id.isEmpty() ? !isProgress(w) : dialogId(w) == id) {
			target = w;
			break;
		}
	}
	if (!target) {
		status = 404;
		return errorJson(QStringLiteral("no_dialog"), id.isEmpty()
			? QStringLiteral("No dialog is open in Daz Studio.")
			: QStringLiteral("That dialog is no longer open."));
	}
	QJsonObject desc = describeDialog(target);
	if (button.isEmpty() && check.isEmpty() && uncheck.isEmpty()) {
		status = 400;
		return errorJson(QStringLiteral("bad_request"), QStringLiteral("Give button (and optionally check/uncheck)."));
	}
	const QStringList missing = setOptions(target, check, uncheck);
	if (!missing.isEmpty()) {
		status = 400;
		return errorJson(QStringLiteral("no_option"), QStringLiteral("No option labeled: %1. Options: %2")
			.arg(missing.join(QStringLiteral(", ")),
				QString::fromUtf8(QJsonDocument(desc.value(QStringLiteral("options")).toArray()).toJson(QJsonDocument::Compact))));
	}
	QString pressed;
	if (!button.isEmpty() && !pressButton(target, button, pressed)) {
		status = 400;
		return errorJson(QStringLiteral("no_button"), QStringLiteral("No button labeled \"%1\". Buttons: %2")
			.arg(button, QString::fromUtf8(QJsonDocument(desc.value(QStringLiteral("buttons")).toArray()).toJson(QJsonDocument::Compact))));
	}
	if (!pressed.isEmpty()) {
		desc.insert(QStringLiteral("answered"), pressed);
		desc.insert(QStringLiteral("answered_by"), QStringLiteral("agent"));
		const QString myId = desc.value(QStringLiteral("id")).toString();
		bool logged = false;
		for (int i = 0; i < m_dialogLog.size(); ++i) {
			if (m_dialogLog.at(i).toObject().value(QStringLiteral("id")).toString() == myId) {
				m_dialogLog.replace(i, desc);
				logged = true;
			}
		}
		if (!logged && m_busy) {
			m_dialogLog.append(desc);
		}
	}
	status = 200;
	return okJson(desc);
}

void DazMcpBridgeServer::respond(QTcpSocket *socket, int status, const QByteArray &body)
{
	QByteArray head;
	head += "HTTP/1.1 " + QByteArray::number(status) + " " + statusText(status) + "\r\n";
	head += "Content-Type: application/json; charset=utf-8\r\n";
	head += "Content-Length: " + QByteArray::number(body.size()) + "\r\n";
	head += "Connection: close\r\n\r\n";
	socket->write(head);
	socket->write(body);
	socket->disconnectFromHost();
}
