// Daz3D-MCP bridge plugin definition.
//
// Starts the local bridge server when Daz Studio loads the plugin and adds a
// "Restart Daz3D-MCP Bridge" action for the rare case it needs a kick.
//
// NOTE: written against the public Daz Studio SDK API; the macro and class
// names must be confirmed against the Daz Studio 6 SDK (still in beta) on the
// first real build. See bridge/README.md.

#include "bridgeserver.h"
#include "version.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QPointer>
#include <QtCore/QTimer>

#include <dzaction.h>
#include <dzapp.h>
#include <dzplugin.h>

namespace {

QPointer<DazMcpBridgeServer> g_server;

void startBridge()
{
	if (!g_server) {
		g_server = new DazMcpBridgeServer(dzApp);
	}
	if (g_server->start()) {
		dzApp->log(QStringLiteral("Daz3D-MCP bridge %1 listening on 127.0.0.1:%2")
			.arg(QStringLiteral(DAZMCP_BRIDGE_VERSION_STRING)).arg(g_server->port()));
	} else {
		dzApp->warning(QStringLiteral("Daz3D-MCP bridge could not start: %1").arg(g_server->lastError()));
	}
}

} // namespace

// Menu action: Window > Daz3D-MCP > Restart bridge (place it with the
// Customize dialog if Daz does not show it automatically).
class DazMcpRestartAction : public DzAction
{
	Q_OBJECT
public:
	DazMcpRestartAction()
		: DzAction(QStringLiteral("Restart Daz3D-MCP Bridge"),
			QStringLiteral("Stops and starts the local bridge used by AI agents."))
	{
	}

protected:
	void executeAction() override
	{
		if (g_server) {
			g_server->stop();
		}
		startBridge();
	}
};

// Start automatically. The plugin library is loaded after the application
// object exists, so a static initializer can queue the start for the first
// turn of the event loop. This avoids depending on a DzPlugin subclass, whose
// constructor differs between SDK versions.
struct DazMcpAutoStart
{
	DazMcpAutoStart()
	{
		QCoreApplication *app = QCoreApplication::instance();
		if (!app) {
			return;
		}
		QTimer::singleShot(0, app, &startBridge);
		QObject::connect(app, &QCoreApplication::aboutToQuit, app, []() {
			if (g_server) {
				g_server->stop();
			}
		});
	}
};
static DazMcpAutoStart g_autoStart;

DZ_PLUGIN_DEFINITION("Daz3D-MCP Bridge");

DZ_PLUGIN_AUTHOR("Daz3D-MCP contributors");
DZ_PLUGIN_VERSION(DAZMCP_BRIDGE_VERSION_MAJOR, DAZMCP_BRIDGE_VERSION_MINOR,
	DAZMCP_BRIDGE_VERSION_REV, DAZMCP_BRIDGE_VERSION_BUILD);
DZ_PLUGIN_DESCRIPTION((
	"Local bridge that lets AI agents control Daz Studio through the Daz3D-MCP server. "
	"Listens only on 127.0.0.1 and requires a token. "
	"<a href=\"https://github.com/MictlanLabs/Daz3D-MCP\">Project page</a>."));

// {7e213815-609e-4791-b826-f7cabdefb811}
DZ_PLUGIN_CLASS_GUID(DazMcpRestartAction, 7e213815, 609e, 4791, b8, 26, f7, ca, bd, ef, b8, 11);

#include "plugin.moc"
