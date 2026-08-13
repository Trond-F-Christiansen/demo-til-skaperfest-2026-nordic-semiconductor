#
# Copyright (c) 2023 Nordic Semiconductor
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#

menu "Trigger"

config CAMERA_TO_WEBSITE_TRIGGER_THREAD_STACK_SIZE
	int "Thread stack size"
	default 512

module = CAMERA_TO_WEBSITE_TRIGGER
module-str = Trigger
source "subsys/logging/Kconfig.template.log_config"

endmenu # Trigger
