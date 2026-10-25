"""Mode-journal recovery and identity tests, independent of native file I/O."""
import unittest

from lab.arp_persistence import ModeJournal, decode, encode


class Files:
    def __init__(self):self.data={};self.fail=False
    def read(self,path):return self.data.get(path)
    def write(self,path,data):
        if self.fail:
            self.data[path]=data[:17]
            raise OSError("injected partial write")
        self.data[path]=data


class ArpPersistenceTests(unittest.TestCase):
    def test_native_project_identity_and_invalid_defaults(self):
        f=Files();j=ModeJournal(f);m=[0]*128;m[0]=3
        self.assertEqual(j.load(128,b"project A"),[0]*128)
        j.save(128,b"project A",m)
        self.assertEqual(j.load(128,b"project A"),m)
        self.assertEqual(j.load(127,b"project A"),[0]*128)
        self.assertEqual(j.load(128,b"project B"),[0]*128)
        blob=next(iter(f.data.values()))
        self.assertIsNone(decode(blob[:-1],128,b"project A"))
        self.assertIsNone(decode(bytes([blob[0]^1])+blob[1:],128,b"project A"))

    def test_inactive_partial_write_keeps_previous_modes(self):
        f=Files();j=ModeJournal(f);m=[1]*128
        j.save(128,b"A",m);f.fail=True
        with self.assertRaises(OSError):j.save(128,b"A",[3]*128)
        self.assertEqual(j.load(128,b"A"),m)

    def test_unknown_existing_file_is_never_overwritten(self):
        f=Files();j=ModeJournal(f);a,b=j.paths(128,b"A")
        f.data[a]=b"user file"
        j.save(128,b"A",[2]*128)
        self.assertEqual(f.data[a],b"user file")
        with self.assertRaises(ValueError):j.save(128,b"A",[3]*128)

    def test_repeated_saves_recall_latest_and_retain_other_project(self):
        f=Files();j=ModeJournal(f)
        for mode in (1,2,3,0):j.save(128,b"A",[mode]*128)
        j.save(128,b"B",[2]*128)
        self.assertEqual(j.load(128,b"A"),[0]*128)
        self.assertEqual(j.load(128,b"B"),[2]*128)

    def test_conflicting_generation_fails_closed_and_ranges_are_checked(self):
        f=Files();j=ModeJournal(f);a,b=j.paths(128,b"A")
        f.data[a]=encode(128,1,b"A",[1]*128);f.data[b]=encode(128,1,b"A",[2]*128)
        self.assertEqual(j.load(128,b"A"),[0]*128)
        with self.assertRaises(ValueError):encode(129,1,b"A",[1]*128)
        with self.assertRaises(ValueError):encode(128,1,b"A",[4]*128)
