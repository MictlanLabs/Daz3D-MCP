// Test stub of the Daz Studio SDK (NOT the real SDK); see ../CMakeLists.txt.
#pragma once
#include <QtCore/QObject>
#include <QtCore/QVariant>
#include <QtCore/QVariantList>
#include <QtCore/QRegularExpression>
// Stub: "executes" by echoing the args back as the DazScript entry would.
class DzScript : public QObject {
public:
	void setCode(const QString &c) { m_code = c; }
	void ref() { ++m_refs; }
	void unref() { if (--m_refs <= 0) delete this; }
	// Like the real SDK: the program ends with "return <entry>(getArguments()[0]);",
	// and the stub echoes that entry name and the first argument back.
	bool execute(const QVariantList &args) {
		if (m_code.contains(QStringLiteral("SYNTAX_ERROR"))) { m_err = QStringLiteral("SyntaxError"); return false; }
		const QRegularExpressionMatch m = QRegularExpression(QStringLiteral(";return (\\w+)\\(getArguments\\(\\)\\[0\\]\\);\\s*$")).match(m_code);
		m_result = QStringLiteral("{\"ok\":true,\"result\":{\"func\":\"%1\",\"args\":%2}}").arg(m.captured(1), args.value(0).toString());
		return true;
	}
	QVariant result() const { return m_result; }
	QString errorMessage() const { return m_err; }
	int errorLine() const { return 3; }
private:
	int m_refs = 0;
	QString m_code, m_err; QVariant m_result;
};
