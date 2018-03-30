##sqlite_data_directory=folder
##dataset=selection TEMP_10MINUTES_RECENT

import sys

print sys.path

from DwdData import DwdData

dwdInterface = DwdData(sqlite_data_directory, dataset)
dwdInterface.execute()
