import sys
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import desktop
from instance import Instance

class DesktopTests(unittest.TestCase):
    def test_second_launch_shows_existing_instance_and_quit_is_explicit(self):
        namespace='test-'+uuid.uuid4().hex
        instances=[]
        try:
            first=Instance(namespace=namespace);instances.append(first)
            second=Instance(namespace=namespace);instances.append(second)
            self.assertTrue(first.owner)
            self.assertFalse(second.owner)
            self.assertEqual(first.command(),'show')
            self.assertIsNone(first.command())
            background=Instance('background',namespace=namespace);instances.append(background)
            self.assertFalse(background.owner)
            self.assertIsNone(first.command())
            quit_request=Instance('quit',namespace=namespace);instances.append(quit_request)
            self.assertFalse(quit_request.owner)
            self.assertEqual(first.command(),'quit')
        finally:
            for instance in reversed(instances):instance.close()

    def test_startup_path_with_spaces_and_opt_out(self):
        with tempfile.TemporaryDirectory(prefix='Cep Kontrol ') as directory:
            executable=Path(directory)/'CepKontrol.exe';executable.touch()
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(executable)), \
                 patch.object(desktop.winreg,'CreateKeyEx',return_value=MagicMock()) as create, \
                 patch.object(desktop.winreg,'SetValueEx') as write,patch.object(desktop.winreg,'DeleteValue') as delete:
                desktop.set_startup(True)
                command=write.call_args.args[-1]
                self.assertTrue(command.startswith('"'+str(executable)+'"'))
                self.assertTrue(command.endswith(' --background'))
                self.assertEqual(create.call_args.args[0],desktop.winreg.HKEY_CURRENT_USER)
                desktop.set_startup(False)
                self.assertEqual(delete.call_args.args[1],'CepKontrol')

if __name__=='__main__':unittest.main()
