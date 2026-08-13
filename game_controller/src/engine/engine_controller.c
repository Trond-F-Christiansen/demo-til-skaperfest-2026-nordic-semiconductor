/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <errno.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include "engine.h"
#include "engine_controller.h"

LOG_MODULE_REGISTER(engine_ctrl);

extern const engine_t kws_engine;
extern const engine_t kws_mine_engine; //model for minesweeper
#if !defined(CONFIG_KWS_ONLY)
extern const engine_t gesture_engine;
#endif

/* Active engine on boot is the first one that initializes; an engine_request_
 * switch() advances to the next available one. CONFIG_KWS_ONLY leaves the
 * gesture engine out of the build entirely, so the app never touches the
 * BMI270 -- optional now that a failing init() only costs that one engine
 * (see engine_controller_init), but it still skips the IMU bring-up.
 */
static const engine_t *const engines[] = {
	&kws_engine,
	&kws_mine_engine,
#if !defined(CONFIG_KWS_ONLY)
	&gesture_engine,
#endif
};

/* Per-engine init() outcome. An engine that failed is never entered: the IMU is
 * powered from the DK, so on a board without it jumpered the gesture engine's
 * init fails while KWS is perfectly usable. */
static bool engine_ready[ARRAY_SIZE(engines)];

static size_t active_idx;
static atomic_t switch_requested;
static atomic_t requested_idx = ATOMIC_INIT(-1);   // -1 = ingen spesifikk, bruk syklisk

/* Next available engine after @p from, wrapping. Returns @p from if it is the
 * only one that came up. */
static size_t next_ready_idx(size_t from)
{
	for (size_t n = 1; n <= ARRAY_SIZE(engines); n++) {
		const size_t i = (from + n) % ARRAY_SIZE(engines);

		if (engine_ready[i]) {
			return i;
		}
	}

	return from;
}

void engine_request_switch(void)
{
	atomic_set(&switch_requested, 1);
}

int engine_request_select(const char *name)
{
	for (size_t i = 0; i < ARRAY_SIZE(engines); i++) {
		if (strcmp(engines[i]->name, name) != 0) {
			continue;
		}

		if (!engine_ready[i]) {
			LOG_WRN("Engine '%s' did not initialize; cannot select it", name);
			return -ENODEV;
		}

		atomic_set(&requested_idx, (atomic_val_t)i);
		atomic_set(&switch_requested, 1);
		return 0;
	}

	LOG_WRN("No engine named '%s'", name);
	return -ENOENT;
}

int engine_controller_init(void)
{
	size_t ready_count = 0;

	for (size_t i = 0; i < ARRAY_SIZE(engines); i++) {
		int err = engines[i]->init();

		if (err) {
			LOG_ERR("Engine '%s' init failed (err %d); it will be unavailable",
				engines[i]->name, err);
			continue;
		}

		engine_ready[i] = true;

		if (ready_count++ == 0) {
			/* Boot on the first engine that came up. */
			active_idx = i;
		}
	}

	if (ready_count == 0) {
		LOG_ERR("No engine initialized");
		return -ENODEV;
	}

	LOG_INF("%u of %u engines available", (unsigned int)ready_count,
		(unsigned int)ARRAY_SIZE(engines));

	return 0;
}

void engine_controller_run(void)
{
	while (true) {
		atomic_clear(&switch_requested);

		const engine_t *e = engines[active_idx];

		LOG_INF("Active engine: %s", e->name);

		int err = e->enter();

		if (err) {
			LOG_ERR("Engine '%s' enter failed (err %d)", e->name, err);
		}

		/* Runs until engine_request_switch() sets the stop flag. */
		e->run(&switch_requested);

		e->exit();

		int want = atomic_set(&requested_idx, -1);
		if (want >= 0) {
			active_idx = (size_t)want;
		} else {
			active_idx = next_ready_idx(active_idx);
		}
	}
}
