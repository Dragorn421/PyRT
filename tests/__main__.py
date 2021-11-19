# run tests with `python3 -m tests`

import unittest

tl = unittest.TestLoader()
ts = tl.discover("tests")
tr = unittest.TextTestRunner()
tr.run(ts)
