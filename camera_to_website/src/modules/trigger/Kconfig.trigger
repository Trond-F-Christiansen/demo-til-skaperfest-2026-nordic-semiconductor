#
# Copyright (c) 2023 Nordic Semiconductor
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#

menu "Trigger"

config LTE_CAMERA_TRIGGER_THREAD_STACK_SIZE
	int "Thread stack size"
	default 512

module = LTE_CAMERA_TRIGGER
module-str = Trigger
source "subsys/logging/Kconfig.template.log_config"

endmenu # Trigger
