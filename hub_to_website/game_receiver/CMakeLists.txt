cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(game_receiver)

target_include_directories(app PRIVATE src)

target_sources(app PRIVATE
  src/main.c
  src/ble/ble_central.c
  src/led_status/led_status.c
  src/score_bridge/score_bridge.c
  src/test_button/test_button.c
)
