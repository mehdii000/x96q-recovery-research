import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
_TMP=tempfile.TemporaryDirectory();_LIB=pathlib.Path(_TMP.name)/'host-slots.so'
subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-O2',str(ROOT/'slots.c'),'-o',str(_LIB)],check=True)
LIB=ctypes.CDLL(str(_LIB))
PROTECT=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int)
class Slot(ctypes.Structure):
    _fields_=[('slot',ctypes.POINTER(ctypes.c_void_p)),('original',ctypes.c_void_p),('replacement',ctypes.c_void_p),('protection',ctypes.c_int)]
for name in ['guard_install_slots','guard_restore_slots']:
    fn=getattr(LIB,name);fn.argtypes=[ctypes.POINTER(Slot),ctypes.c_size_t,PROTECT];fn.restype=ctypes.c_int

class SlotTests(unittest.TestCase):
    def fixture(self):
        values=(ctypes.c_void_p*2)(0x1000,0x2000)
        slots=(Slot*2)(Slot(ctypes.cast(ctypes.byref(values,0),ctypes.POINTER(ctypes.c_void_p)),0x1000,0x3000,1),Slot(ctypes.cast(ctypes.byref(values,ctypes.sizeof(ctypes.c_void_p)),ctypes.POINTER(ctypes.c_void_p)),0x2000,0x4000,1))
        return values,slots

    def test_install_then_restore_recovers_both_original_pointers(self):
        values,slots=self.fixture();calls=[]
        protect=PROTECT(lambda p,n,mode:(calls.append((p,n,mode)) or 0))
        self.assertEqual(LIB.guard_install_slots(slots,2,protect),1)
        self.assertEqual(list(values),[0x3000,0x4000])
        self.assertEqual(LIB.guard_restore_slots(slots,2,protect),1)
        self.assertEqual(list(values),[0x1000,0x2000])
        self.assertTrue(all(n==4096 for _,n,_ in calls))
        self.assertEqual(calls[-1][2],1)

    def test_protection_restore_failure_rolls_back_a_written_slot(self):
        values,slots=self.fixture();calls=[]
        def change(p,n,mode):
            calls.append(mode)
            return -1 if len(calls)==2 else 0
        protect=PROTECT(change)
        self.assertEqual(LIB.guard_install_slots(slots,2,protect),0)
        self.assertEqual(list(values),[0x1000,0x2000])
        self.assertEqual(calls,[3,1,3,1])

    def test_later_slot_failure_rolls_back_previously_installed_slot(self):
        values,slots=self.fixture();calls=[]
        def change(p,n,mode):
            calls.append(mode)
            return -1 if len(calls)==3 else 0
        protect=PROTECT(change)
        self.assertEqual(LIB.guard_install_slots(slots,2,protect),0)
        self.assertEqual(list(values),[0x1000,0x2000])

if __name__=='__main__':unittest.main()
