# Daz3D-MCP bridge plugin.
#
# Build for Daz Studio 6 (Qt 6.10, Daz Studio 6 SDK):
#   cmake -S bridge -B build -DDAZ_SDK_DIR=/path/to/DAZStudio6SDK -DCMAKE_PREFIX_PATH=/path/to/Qt/6.10.x/macos
#   cmake --build build --config Release
#
# The result is bridge/build/.../dazmcp_bridge.dylib (macOS) or dazmcp_bridge.dll (Windows).
cmake_minimum_required(VERSION 3.21)
project(dazmcp_bridge VERSION 0.1.0 LANGUAGES CXX)

set(DAZ_SDK_DIR "" CACHE PATH "Root folder of the Daz Studio SDK (contains include/ and lib/)")
if(NOT DAZ_SDK_DIR)
  message(FATAL_ERROR "Set DAZ_SDK_DIR to the Daz Studio 6 SDK folder.")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.2 REQUIRED COMPONENTS Core Gui Widgets Network)

find_path(DAZ_SDK_INCLUDE_DIR dzapp.h
  PATHS "${DAZ_SDK_DIR}/include" "${DAZ_SDK_DIR}"
  NO_DEFAULT_PATH REQUIRED)

find_library(DAZ_CORE_LIBRARY NAMES dzcore
  PATHS
    "${DAZ_SDK_DIR}/lib/x64"
    "${DAZ_SDK_DIR}/lib/Mac64"
    "${DAZ_SDK_DIR}/lib/macos"
    "${DAZ_SDK_DIR}/lib"
  NO_DEFAULT_PATH REQUIRED)

add_library(dazmcp_bridge MODULE
  src/plugin.cpp
  src/bridgeserver.cpp
  src/bridgeserver.h
  src/version.h
)

target_include_directories(dazmcp_bridge PRIVATE "${DAZ_SDK_INCLUDE_DIR}")
target_link_libraries(dazmcp_bridge PRIVATE
  "${DAZ_CORE_LIBRARY}"
  Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Network)

if(WIN32)
  target_compile_definitions(dazmcp_bridge PRIVATE UNICODE _UNICODE NOMINMAX)
  set_target_properties(dazmcp_bridge PROPERTIES PREFIX "" SUFFIX ".dll")
elseif(APPLE)
  # Daz Studio loads plugins as .dylib files.
  set_target_properties(dazmcp_bridge PROPERTIES PREFIX "" SUFFIX ".dylib")
  # Resolve Qt and dzcore from the running Daz Studio, not from the build machine.
  target_link_options(dazmcp_bridge PRIVATE -undefined dynamic_lookup)
endif()

install(TARGETS dazmcp_bridge LIBRARY DESTINATION . RUNTIME DESTINATION .)
