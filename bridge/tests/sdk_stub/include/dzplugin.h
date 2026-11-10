// Test stub of the Daz Studio SDK (NOT the real SDK); see ../CMakeLists.txt.
#pragma once
#define DZ_PLUGIN_DEFINITION(name) static const char *dz_plugin_name = name
#define DZ_PLUGIN_AUTHOR(a) static const char *dz_plugin_author = a
#define DZ_PLUGIN_VERSION(a, b, c, d) static const int dz_plugin_version[] = {a, b, c, d}
#define DZ_PLUGIN_DESCRIPTION(d) static const char *dz_plugin_desc = d
#define DZ_PLUGIN_CLASS_GUID(cls, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8) static cls *dz_unused_##cls = nullptr
