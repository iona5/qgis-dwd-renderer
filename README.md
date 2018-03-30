# qgis-dwd-renderer

This collection of files was created to provide a general way to convert time series data, specifically data from the DWD into map sequences via the API of the GIS application Quantum GIS 2.18.

In general there are two steps involved:
* First downloading the data files from DWD and converting into SQLite databases (DwdData.py).
* Then creating the image sequences through the QGIS API (displaylayer_update_stdl.py).

Please note that you need to have the correct environment when executing. Under Windows open a cmd process, execute c:\<PATH_TO_QGIS>\bin\o4w_env.bat and use the QGIS supplied python.exe (c:\<PATH_TO_QGIS>\bin\python.exe)
