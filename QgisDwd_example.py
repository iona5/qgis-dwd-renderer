import os, sys

QGIS_PREFIX_PATH = 'C:/Program Files/QGIS 2.18/apps/qgis-ltr'

# Append QGIS Python library to python search path
sys.path.append(QGIS_PREFIX_PATH + '/python')
sys.path.append(QGIS_PREFIX_PATH + '/python/plugins')

# Append location of DLLs to current system PATH envrionment variable
os.environ['PATH'] += ";" + QGIS_PREFIX_PATH + "/bin"
# THIS SEEMS TO WORK!!!
os.environ['QGIS_PREFIX_PATH'] = QGIS_PREFIX_PATH

from QgisDwd import *

# static:
# take displayLayerFile (in this case "C:/dwd-qgis/input/stations_10min_voronoi.shp")
# and join data and just render it
renderer = StaticQgisDwdRenderer(
"C:/dwd-qgis/input/databases/split_10min_tu_%s.sqlite",
"C:/dwd-qgis/input/layer_style.qml",
"C:/dwd-qgis/input/composer_template.qpt",
"C:/dwd-qgis/result/",
"C:/dwd-qgis/input/stations_10min_voronoi.shp"
)
renderer.execute("20170405", "20170406", 1)

# dynamic:
# after joining data to a point layer, filter stations with missing data.
# then generate voronoi map from that layer and optionally clip it.
renderer = DynamicQgisDwdRenderer(
"C:/dwd-qgis/input/databases/split_10min_tu_%s.sqlite",
"C:/dwd-qgis/input/layer_style.qml",
"C:/dwd-qgis/input/composer_template.qpt",
"C:/dwd-qgis/result/",
"C:/dwd-qgis/input/stations_10min_32632.shp",
clipLayerFile = "C:/dwd-qgis/input/germany_32632.shp"
)
renderer.execute("20170401", "20170402", useCounterForName = True)
