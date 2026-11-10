// Test stub of the Daz Studio SDK (NOT the real SDK); see ../CMakeLists.txt.
#pragma once
#include <QtGui/QAction>
class DzAction : public QAction {
public:
	DzAction(const QString &text, const QString &desc) : QAction(text, nullptr) { Q_UNUSED(desc); }
protected:
	virtual void executeAction() {}
};
