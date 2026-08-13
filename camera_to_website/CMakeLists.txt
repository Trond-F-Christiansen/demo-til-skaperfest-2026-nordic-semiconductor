#
# Copyright (c) 2023 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(camera_to_website)

# Out-of-tree binding for the Arducam Mega node in the board overlay
list(APPEND DTS_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/dts)

# Include files that are common for all modules
add_subdirectory(src/common)

# Out-of-tree camera driver
target_sources(app PRIVATE src/drivers/arducam_mega.c)

# Include mandatory module source folders
add_subdirectory(src/modules/trigger)
add_subdirectory(src/modules/camera)
add_subdirectory(src/modules/network)
add_subdirectory(src/modules/transport)
add_subdirectory(src/modules/error)

# Optional modules
add_subdirectory_ifdef(CONFIG_CAMERA_TO_WEBSITE_LED src/modules/led)
