/* 2026-07-06T12:26:35.758861 */

/*
* Copyright (c) 2026 Nordic Semiconductor ASA
* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
*/

#ifndef _NRF_EDGEAI_USER_MODEL_LABELS_H_
#define _NRF_EDGEAI_USER_MODEL_LABELS_H_

#include <nrf_edgeai/nrf_edgeai_ctypes.h>

#ifdef   __cplusplus
extern "C"
{
#endif

typedef enum nrf_edgeai_user_label_e {
    MODEL_LABEL_INDEX_OTHER,
    MODEL_LABEL_INDEX_SILENCE,
    MODEL_LABEL_INDEX_FIVE,
    MODEL_LABEL_INDEX_FLAG,
    MODEL_LABEL_INDEX_FOUR,
    MODEL_LABEL_INDEX_NO,
    MODEL_LABEL_INDEX_ONE,
    MODEL_LABEL_INDEX_OPEN,
    MODEL_LABEL_INDEX_RESET,
    MODEL_LABEL_INDEX_SEVEN,
    MODEL_LABEL_INDEX_SIX,
    MODEL_LABEL_INDEX_THREE,
    MODEL_LABEL_INDEX_TWO,
    MODEL_LABEL_INDEX_ZERO,
} nrf_edgeai_user_label_t;

static const char* NRF_EDGEAI_USER_LABELS_NAME[] = {
    "OTHER", "SILENCE", "five", "flag", "four", "no", "one", "open", "reset", "seven", "six", "three", "two", "zero"
};

#ifdef   __cplusplus
}
#endif

#endif /* _NRF_EDGEAI_USER_MODEL_LABELS_H_ */
