# Builds a STUB of the Daz Studio SDK plus a host program that loads the bridge
# module like Daz Studio does. Used by CI on Linux to compile and exercise the
# Qt side of the bridge (HTTP, token, security checks) without Daz Studio.
# It is not the real SDK and proves nothing about the Daz API calls.
cmake_minimum_required(VERSION 3.21)
project(dazmcp_sdk_stub CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(Qt6 REQUIRED COMPONENTS Core Widgets)

add_library(dzcore SHARED dzcore.cpp)
set_target_properties(dzcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/lib)

add_executable(bridge_host host.cpp)
target_include_directories(bridge_host PRIVATE include)
target_link_libraries(bridge_host Qt6::Core Qt6::Widgets)
