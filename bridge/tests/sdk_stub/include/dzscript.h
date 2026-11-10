// Test stub of the Daz Studio SDK (NOT the real SDK); see ../CMakeLists.txt.
#pragma once
#include <QtCore/QObject>
#include <QtCore/QVariant>
#include <QtCore/QVariantList>
// Stub: "executes" by echoing the args back as the DazScript entry would.
class DzScript : public QObject {
public:
	void setCode(const QString &c) { m_code = c; }
	bool call(const QString &func, const QVariantList &args) {
		if (m_code.contains(QStringLiteral("SYNTAX_ERROR"))) { m_err = QStringLiteral("SyntaxError"); return false; }
		m_result = QStringLiteral("{\"ok\":true,\"result\":{\"func\":\"%1\",\"args\":%2}}").arg(func, args.value(0).toString());
		return true;
	}
	QVariant result() const { return m_result; }
	QString errorMessage() const { return m_err; }
	int errorLine() const { return 3; }
private:
	QString m_code, m_err; QVariant m_result;
};
