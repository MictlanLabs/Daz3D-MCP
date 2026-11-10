// Test stub of the Daz Studio SDK (NOT the real SDK).
#pragma once
#include <QtWidgets/QApplication>
#include <QtCore/QString>
#include <cstdio>
class DzApp : public QApplication {
public:
	DzApp(int &c, char **v) : QApplication(c, v) {}
	QString getLongVersionString() const { return QStringLiteral("6.25.0.0-stub"); }
	void log(const QString &m) { std::fprintf(stderr, "LOG %s\n", qPrintable(m)); }
	void warning(const QString &m) { std::fprintf(stderr, "WARN %s\n", qPrintable(m)); }
};
#define dzApp (static_cast<DzApp *>(QCoreApplication::instance()))
