// Daz3D-MCP bridge: a tiny HTTP server inside Daz Studio.
//
// It only listens on 127.0.0.1, requires a bearer token and does exactly one
// thing: run a DazScript function on the main thread and return its result.
// All real logic lives in the DazScript library shipped with the MCP server.
#pragma once

#include <QtCore/QByteArray>
#include <QtCore/QHash>
#include <QtCore/QObject>
#include <QtCore/QString>
#include <QtNetwork/QTcpServer>

class QTcpSocket;

class DazMcpBridgeServer : public QObject
{
	Q_OBJECT
public:
	explicit DazMcpBridgeServer(QObject *parent = nullptr);
	~DazMcpBridgeServer() override;

	// Starts listening. Returns false and fills lastError() on failure.
	bool start();
	void stop();
	bool isRunning() const;
	quint16 port() const;
	QString lastError() const;

	// Folder that holds token and bridge.json (~/.daz3d-mcp).
	static QString configDir();

private slots:
	void onNewConnection();
	void onReadyRead();
	void onDisconnected();

private:
	struct Request
	{
		QString method;
		QString path;
		QHash<QString, QString> headers; // lower-case names
		QByteArray body;
	};

	// Returns true when a complete request was parsed out of buffer.
	bool tryParse(QByteArray &buffer, Request &req, int &errorStatus) const;
	void handle(QTcpSocket *socket, const Request &req);
	QByteArray execute(const QByteArray &body, int &status);
	void respond(QTcpSocket *socket, int status, const QByteArray &body);
	bool isAuthorized(const Request &req) const;
	bool isLocalHost(const Request &req) const;

	bool loadOrCreateToken();
	bool writeDiscoveryFile() const;
	void removeDiscoveryFile() const;

	QTcpServer *m_server;
	QHash<QTcpSocket *, QByteArray> m_buffers;
	QByteArray m_token;
	QString m_lastError;
	bool m_busy;
};
