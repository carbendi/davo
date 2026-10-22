import unittest
from input_engine import InputEngine
from transport import Transport


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.transport = Transport(self.actions.append)
        self.source = {'action': 'transport', 'hw_mode': 'Jog', 'jog_units': 128}
        self.transport.configure(self.source)

    def shortcuts(self):
        return [a['shortcuts'] for a in self.actions]

    def test_shuttle_stays_at_speed_without_repeating_and_zero_stops(self):
        self.transport.select('Shuttle')
        self.transport.turn('shuttle', 400)
        self.transport.turn('shuttle', 500)
        self.assertEqual(self.shortcuts(), [['k', 'l']])
        self.transport.turn('shuttle', 0)
        self.assertEqual(self.shortcuts(), [['k', 'l'], ['k']])
        self.assertFalse(self.transport.playing)

    def test_shuttle_accelerates_decelerates_and_reverses(self):
        self.transport.select('Shuttle')
        for value in (400, 2400, 400, -400):
            self.transport.turn('shuttle', value)
        self.assertEqual(self.shortcuts(), [['k', 'l'], ['k', 'l', 'l', 'l'], ['k', 'l'], ['k', 'j']])

    def test_shuttle_hysteresis_and_maximum(self):
        self.transport.select('Shuttle')
        for value in (400, 1030, 1080):
            self.transport.turn('shuttle', value)
        self.assertEqual(len(self.actions), 1)
        self.transport.turn('shuttle', 1120)
        self.assertEqual(self.transport.level, 2)
        self.transport.turn('shuttle', 1000000)
        self.assertEqual(self.shortcuts()[-1], ['k', 'l', 'l', 'l', 'l'])

    def test_reselect_shuttle_stops_and_recentres(self):
        self.transport.select('Shuttle')
        self.transport.turn('shuttle', 400)
        epoch = self.transport.epoch
        self.transport.select('Shuttle')
        self.assertEqual(self.shortcuts()[-1], ['k'])
        self.assertGreater(self.transport.epoch, epoch)

    def test_small_jog_motion_accumulates_and_large_motion_is_bounded(self):
        for _ in range(3):
            self.transport.turn('jog', 32)
        self.assertEqual(self.actions, [])
        self.transport.turn('jog', 32)
        self.assertEqual(self.shortcuts(), [['right']])
        self.transport.turn('jog', -256)
        self.assertEqual(self.shortcuts()[-1], ['left', 'left'])
        self.transport.turn('jog', 2**31-1)
        self.assertEqual(len(self.shortcuts()[-1]), 20)
        self.assertLess(abs(self.transport.remainder), 128)

    def test_scroll_has_larger_steps_and_rejects_stale_hardware_mode(self):
        self.transport.select('Scroll')
        self.transport.turn('jog', 128)
        self.assertEqual(self.actions, [])
        self.transport.turn('scroll', 128)
        self.assertEqual(self.shortcuts(), [['right']*10])

    def test_stop_play_requires_neutral_before_shuttle_resumes(self):
        self.transport.select('Shuttle')
        self.transport.turn('shuttle', 400)
        self.transport.play_stop()
        self.transport.turn('shuttle', 450)
        self.assertFalse(self.transport.playing)
        self.transport.turn('shuttle', 0)
        self.transport.turn('shuttle', 450)
        self.assertTrue(self.transport.playing)

    def test_rejected_command_requires_neutral_and_does_not_claim_playing(self):
        self.transport.perform = lambda action: False
        self.transport.select('Shuttle')
        self.transport.turn('shuttle', 400)
        self.assertFalse(self.transport.playing)
        self.assertTrue(self.transport.neutral_required)
        self.transport.perform = self.actions.append
        self.transport.turn('shuttle', 450)
        self.assertEqual(self.actions, [])
        self.transport.turn('shuttle', 0)
        self.transport.turn('shuttle', 450)
        self.assertTrue(self.transport.playing)

    def test_source_change_stops_using_original_stop_key(self):
        self.transport.configure(dict(self.source, stop_key='s'))
        self.transport.select('Shuttle')
        self.transport.turn('shuttle', 400)
        self.transport.configure(dict(self.source, stop_key='t'))
        self.assertEqual(self.shortcuts()[-1], ['s'])

    def test_sensitivity_zero_stops_playback(self):
        self.transport.select('Shuttle')
        self.transport.turn('shuttle', 400)
        self.transport.configure(dict(self.source, sensitivity=0))
        self.transport.turn('shuttle', 400)
        self.assertFalse(self.transport.playing)
        self.assertEqual(self.shortcuts()[-1], ['k'])

    def test_engine_buttons_and_disconnect(self):
        config = {'layers': {'default': {'buttons': {'SHTL': {'action': 'hotkey', 'keys': 'x'}}, 'dial_default': self.source}}}
        engine = InputEngine(config, self.actions.append, lambda k: None, lambda k: None)
        engine.keys_changed(['SHTL'])
        self.assertEqual(engine.dial_source()['hw_mode'], 'Shuttle')
        engine.jog('shuttle', 400)
        engine.disconnected()
        self.assertEqual(self.shortcuts(), [['k', 'l'], ['k']])

    def test_non_transport_mode_preserves_custom_button_mapping(self):
        config = {'layers': {'default': {'buttons': {'SHTL': {'action': 'hotkey', 'keys': 'x'}}}}}
        engine = InputEngine(config, self.actions.append, lambda k: None, lambda k: None)
        engine.keys_changed(['SHTL'])
        self.assertEqual(self.actions, [{'action': 'hotkey', 'keys': 'x'}])

    def test_reset_releases_modifiers_before_sending_stop(self):
        config = {'layers': {'default': {'buttons': {}, 'dial_default': self.source}}}
        events = []
        engine = InputEngine(config, events.append, lambda k: None, lambda k: events.append(('release', k)))
        engine.keys_changed(['SHTL'])
        engine.jog('shuttle', 400)
        engine.keys('ctrl', True)
        events.clear()
        engine.reset()
        self.assertEqual(events[0], ('release', 'ctrl'))
        self.assertEqual(events[1]['shortcuts'], ['k'])
