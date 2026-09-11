# SPDX-License-Identifier: AGPL-3.0-or-later
"""Set HHKB_STOCK_HFB to the exact official A0.48 image; see README."""
import hashlib
import os
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hhkb_v013_generic_hold_builder_v0_2_rc2 as builder
from hhkb_emulator import Scanner


class HoldRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        filename=os.environ.get('HHKB_STOCK_HFB')
        if not filename:
            raise RuntimeError('HHKB_STOCK_HFB must point to the exact official A0.48 HFB')
        cls.stock=Path(filename).read_bytes()
        builder.validate_stock(cls.stock)
        cls.images={}
        for spec in ['SPACE>SPACE>FN:250','A>A>CTRL:250','A>A>LALT:250',
                     'A>A>V:250','A>A>SPACE:250']:
            cls.images[spec]=builder.build(cls.stock,[builder.parse_slot(spec)])[0]

    def report(self,m):
        return bytes(m.uc.mem_read(0x2000065d,8))

    def test_ctrl_release_orders(self):
        for spec,image in self.images.items():
            source=builder.parse_slot(spec)['source']
            target=builder.parse_slot(spec)['hold']
            for before in [False,True]:
                for ctrl_first in [False,True]:
                    with self.subTest(spec=spec,before=before,ctrl_first=ctrl_first):
                        m=Scanner(image);m.settle(0,[])
                        if before:m.settle(5,[3])
                        m.settle(10,[source,3] if before else [source])
                        m.settle(300,[source,3]);self.assertEqual(self.report(m)[0]&1,1)
                        m.settle(310,[source] if ctrl_first else [3])
                        # Physical Ctrl must release unless synthetic target is Ctrl.
                        self.assertEqual(self.report(m)[0]&1,int(not ctrl_first or target==3))
                        m.settle(320,[]);m.settle(340,[])
                        self.assertEqual(self.report(m),bytes(8))
                        self.assertEqual(m.byte(0x20000068),0)

    def test_regression_detects_original_branch(self):
        original=bytearray(self.images['SPACE>SPACE>FN:250'])
        self.assertEqual(original[0xf112:0xf114],bytes.fromhex('00 bf'))
        original[0xf112:0xf114]=bytes.fromhex('17 d0')
        # Direct emulation does not consume the HFB CRC header.
        m=Scanner(bytes(original));m.settle(0,[]);m.settle(10,[48]);m.settle(300,[48,3])
        m.settle(310,[48]);m.settle(320,[])
        self.assertEqual(self.report(m)[0],1)
        m.settle(330,[27]);self.assertEqual(self.report(m),bytes.fromhex('01 00 04 00 00 00 00 00'))

    def test_stock_control(self):
        m=Scanner(self.stock);m.settle(0,[]);m.settle(10,[107]);m.settle(300,[107,3])
        m.settle(310,[107]);m.settle(320,[])
        self.assertEqual(self.report(m),bytes(8))

    def test_spacefn_modifiers_and_native_fn_overlap(self):
        image=self.images['SPACE>SPACE>FN:250']
        for key in [3,0,112,24,32,104,107]:
            for physical_first in [False,True]:
                for source_first_up in [False,True]:
                    with self.subTest(key=key,physical_first=physical_first,source_first_up=source_first_up):
                        m=Scanner(image);m.settle(0,[])
                        m.settle(5,[key] if physical_first else [48])
                        m.settle(10,[48,key]);m.settle(300,[48,key])
                        m.settle(310,[key] if source_first_up else [48])
                        if key==107:self.assertEqual(m.byte(0x20000068),1)
                        m.settle(320,[]);m.settle(340,[])
                        self.assertEqual(self.report(m),bytes(8))
                        self.assertEqual(m.byte(0x20000068),0)

    def test_threshold_and_tick_wrap(self):
        for start in [10,0xfffffff0]:
            with self.subTest(start=start):
                m=Scanner(self.images['SPACE>SPACE>FN:250']);m.scan(start-1,[])
                m.scan(start,[48]);m.scan(start+249,[48])
                self.assertEqual(m.byte(0x20000068),0)
                m.scan(start+250,[48]);self.assertEqual(m.byte(0x20000068),1)
                m.settle(start+260,[]);self.assertEqual(m.byte(0x20000068),0)
                self.assertEqual(self.report(m),bytes(8))

    def test_tap_and_fn_mapping(self):
        m=Scanner(self.images['SPACE>SPACE>FN:250']);m.settle(0,[])
        m.settle(10,[48]);self.assertEqual(self.report(m),bytes(8))
        m.settle(30,[]);self.assertIn(0x2c,self.report(m)[2:])
        m.settle(50,[]);self.assertEqual(self.report(m),bytes(8))
        m.settle(100,[48]);m.settle(400,[48]);m.settle(410,[48,27])
        self.assertIn(0x50,self.report(m)[2:])
        m.settle(420,[48]);m.settle(430,[]);self.assertEqual(self.report(m),bytes(8))

    def test_repeated_ctrl_spacefn(self):
        m=Scanner(self.images['SPACE>SPACE>FN:250']);m.settle(0,[])
        for n in range(50):
            t=10+n*400
            m.settle(t,[48]);m.settle(t+260,[48,3]);m.settle(t+270,[48]);m.settle(t+280,[])
            self.assertEqual(self.report(m),bytes(8),n)
            self.assertEqual(m.byte(0x20000068),0,n)

    def test_all_space_ctrl_event_orders(self):
        # All six valid orders of two key-down/key-up pairs, at multiple timings.
        events=[(48,True),(48,False),(3,True),(3,False)]
        for order in itertools.permutations(events):
            if any(order.index((key,True))>order.index((key,False)) for key in (48,3)):
                continue
            for gap in [10,249,250,251,300]:
                with self.subTest(order=order,gap=gap):
                    m=Scanner(self.images['SPACE>SPACE>FN:250']);m.settle(0,[])
                    pressed=set()
                    for n,(key,down) in enumerate(order):
                        if down:pressed.add(key)
                        else:pressed.remove(key)
                        m.settle(10+n*gap,pressed)
                    m.settle(40+4*gap,[])
                    self.assertEqual(self.report(m),bytes(8))
                    self.assertEqual(m.byte(0x20000068),0)

    def test_binary_scope_crc_and_reference(self):
        # Fix changes only this instruction within the executable core.
        core=builder.HHPATCH.apply_generic_hold_core(self.stock)
        old_reference=bytearray(self.images['A>A>LALT:250'])
        old_reference[0xf112:0xf114]=bytes.fromhex('17 d0')
        old_reference[2:4]=builder.crc16_ref(old_reference[4:65540]).to_bytes(2,'little')
        old_reference[:2]=builder.crc16_ref(old_reference[2:]).to_bytes(2,'little')
        self.assertEqual(hashlib.sha256(old_reference).hexdigest(),
                         '2d39137c42d225d4ec80036f5bc43952b3d723db9b9546def77510721a51484d')
        self.assertEqual(core[0xf112:0xf114],bytes.fromhex('00 bf'))
        for image in self.images.values():
            self.assertEqual(len(image),len(self.stock))
            self.assertEqual(builder.crc16_ref(image[4:65540]),int.from_bytes(image[2:4],'little'))
            self.assertEqual(builder.crc16_ref(image[2:]),int.from_bytes(image[:2],'little'))
            differences={i for i,(a,b) in enumerate(zip(core,image)) if a!=b}
            self.assertLessEqual(differences,set(range(4))|set(range(0xeea8,0xeee8)))
        self.assertEqual(hashlib.sha256(self.images['A>A>LALT:250']).hexdigest(),builder.GENERIC_CORE_REFERENCE_SHA256)


if __name__=='__main__':unittest.main()
