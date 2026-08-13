/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup engine_controller Inference engine controller
 * @{
 * @ingroup game_controller
 *
 * @brief Owns the set of inference engines, runs the active one, and switches
 *        between them on request.
 */
#ifndef __ENGINE_CONTROLLER_H__
#define __ENGINE_CONTROLLER_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * @brief Initialize all registered engines (one-time hardware + model init).
 *
 * An engine whose init() fails is logged and marked unavailable rather than
 * failing the whole application: a missing IMU should cost the gesture engine,
 * not the boot. @ref engine_request_select refuses unavailable engines.
 *
 * @retval 0 if at least one engine came up.
 * @retval -ENODEV if every engine failed to initialize.
 */
int engine_controller_init(void);

/**
 * @brief Run the active engine, switching to the next on request.
 *
 * Does not return.
 */
void engine_controller_run(void);

/**
 * @brief Request a switch to the next engine.
 *
 * Safe to call from another context (e.g. the button click handler). The switch
 * takes effect when the active engine next checks its stop flag. Engines that
 * failed to initialize are skipped.
 */
void engine_request_switch(void);

/**
 * @brief Request a switch to a specific engine by name.
 *
 * Safe to call from another context (e.g. the button click handler). Like
 * @ref engine_request_switch, the switch takes effect when the active engine
 * next checks its stop flag.
 *
 * @param name One of the @c ENGINE_NAME_* strings in engine.h.
 *
 * @retval 0 on success.
 * @retval -ENOENT if no engine is registered under @p name.
 * @retval -ENODEV if that engine failed to initialize and is unavailable.
 */
int engine_request_select(const char *name);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __ENGINE_CONTROLLER_H__ */

/**
 * @}
 */
