import importlib.util
from pathlib import Path
import struct
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch


class HidOutputTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('test_hid_output_module', Path(__file__).parents[1]/'hid_layer.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'hid': MagicMock()}):
            spec.loader.exec_module(self.module)
        self.device = object.__new__(self.module.SpeedEditor)
        self.device.dev = MagicMock()
        self.device.dev.write.return_value = 7
        self.device._io_lock = threading.RLock()
        self.device._closed = False

    def test_mode_and_led_reports_have_expected_ids_masks_and_sizes(self):
        self.device.set_jog_mode(self.module.JogMode.ABSOLUTE_DEADZERO)
        self.device.set_jog_leds(self.module.JogLed.SHTL)
        self.device.set_leds(self.module.Led.CUT | self.module.Led.CAM1)
        reports = [call.args[0] for call in self.device.dev.write.call_args_list]
        self.assertEqual(reports, [struct.pack('<BBIB', 3, 3, 0, 255), b'\x04\x02', struct.pack('<BI', 2, (1<<1)|(1<<14))])

    def test_closed_or_rejected_output_raises_instead_of_claiming_success(self):
        self.device._closed = True
        with self.assertRaises(OSError):
            self.device.set_jog_leds(1)
        self.device.dev.write.assert_not_called()
        self.device._closed = False
        self.device.dev.write.return_value = -1
        with self.assertRaises(OSError):
            self.device.set_leds(0)
