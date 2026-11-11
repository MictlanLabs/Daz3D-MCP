// Test host: loads the bridge module like Daz Studio does.
// usage: bridge_host <module> <seconds>
// Loads the bridge module like Daz Studio would and runs the event loop.
#include <dzapp.h>
#include <QtCore/QLibrary>
#include <QtCore/QTimer>
#include <cstdio>
int main(int argc, char **argv) {
	qputenv("QT_QPA_PLATFORM", "offscreen");
	DzApp app(argc, argv);
	// Daz has a main window; here a closed test dialog must not end the app.
	app.setQuitOnLastWindowClosed(false);
	QLibrary lib(QString::fromLocal8Bit(argv[1]));
	if (!lib.load()) { std::fprintf(stderr, "load failed: %s\n", qPrintable(lib.errorString())); return 2; }
	QTimer::singleShot(atoi(argv[2]) * 1000, &app, &QCoreApplication::quit);
	return app.exec();
}
