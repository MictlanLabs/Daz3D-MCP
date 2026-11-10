#include "bridgeserver.h"
#include "version.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QRandomGenerator>
#include <QtCore/QSaveFile>
#include <QtCore/QVariantList>
#include <QtNetwork/QHostAddress>
#include <QtNetwork/QTcpSocket>

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

} // namespace

DazMcpBridgeServer::DazMcpBridgeServer(QObject *parent)
	: QObject(parent), m_server(new QTcpServer(this)), m_busy(false)
{
	connect(m_server, &QTcpServer::newConnection, this, &DazMcpBridgeServer::onNewConnection);
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
		respond(socket, 200, QJsonDocument(obj).toJson(QJsonDocument::Compact));
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

	m_busy = true;
	DzScript script;
	script.setCode(code);
	const bool ok = script.call(entry, QVariantList() << args);
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
	m_busy = false;
	status = 200;
	return out;
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
