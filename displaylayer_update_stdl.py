import os, sys

# Append QGIS Python library to python search path
sys.path.append('C:/Program Files/QGIS 2.18/apps/qgis-ltr/python')
sys.path.append('C:/Program Files/QGIS 2.18/apps/qgis-ltr/python/plugins')

# Append location of DLLs to current system PATH envrionment variable
os.environ['PATH'] += ";C:/Program Files/QGIS 2.18/apps/qgis-ltr/bin"
# THIS SEEMS TO WORK!!!
os.environ['QGIS_PREFIX_PATH'] = "c:/Program Files/QGIS 2.18/apps/qgis-ltr"

# Examine new PATH environment variable
#print os.environ['PATH']


from qgis.core import *

# THIS DOES NOT WORK!!!
#QgsApplication.setPrefixPath("c:/Program Files/QGIS 2.18/apps/qgis-ltr", False)


qgs = QgsApplication([],True)
qgs.initQgis()

import qgis
import os.path
from datetime import datetime
from datetime import timedelta
import time
from PyQt4.QtXml import QDomDocument
from PyQt4.QtCore import QTimer
import processing
from processing.core.Processing import Processing

# timespan to render, format YYYYmmdd
START="20161117"
END="20161120"

# the amount of images the script should actually render, useful for debugging
# to stop the script early, setting this to 0 will render the whole timespan
RENDER_LIMIT=0

# folder where to put the image sequence
RESULT_FOLDER="C:/dwd-qgis/result/"

# which composer template to use (extension .qpt)
COMPOSER_TEMPLATE="C:/dwd-qgis/input/composer_template.qpt"
# which style file to apply to the display layer (extension .qml)
VORONOI_LAYERSTYLE="C:/dwd-qgis/input/layer_style.qml"

# if the display layer should be clipped after applying the data
DO_CLIP=False

# if the composer map should be zoomed to a specific extent, define another
# shapefile here. the composer map will be zoomed to the bounding box all the
# features. Set to None if no zoom should be executed.
ZOOM_TO_SHAPEFILE="C:/dwd-qgis/input/zoomExtent.shp"



project = QgsProject.instance()
mapRegistry = QgsMapLayerRegistry.instance()


DATA_LAYER_FORMAT="%s station_data"

# display layer to use in the static case (not recreating between runs), needs
# to contain the referenced join field
STATIC_DISPLAY_LAYER = QgsVectorLayer("C:/dwd-qgis/input/stations_display.shp", "stations_10min_voronoi", "ogr")
QgsMapLayerRegistry.instance().addMapLayer(STATIC_DISPLAY_LAYER)

STATIONS_LAYER=QgsVectorLayer("C:/dwd-qgis/input/stations_10min_32632.shp", "stations_10min_32632", "ogr")
QgsMapLayerRegistry.instance().addMapLayer(STATIONS_LAYER)



if(DO_CLIP):
    CLIP_LAYER=QgsVectorLayer("C:/dwd-qgis/input/germany_32632.shp", "clip layer", "ogr")
    QgsMapLayerRegistry.instance().addMapLayer(CLIP_LAYER)

# load sqlite3 files in a very stupid way:
for month in ( 201607, 201608, 201609, 201610, 201611, 201612, 201701, 201702, 201703, 201704, 201705, 201706, 201707, 201708, 201709, 201710, 201711, 201712, 201801 ):
    print "load data layer %s" % month
    dataLayer = QgsVectorLayer("C:/dwd-qgis/input/databases/split_10min_tu_%s.sqlite" % month, DATA_LAYER_FORMAT % month, "ogr")
    #print dataLayer.isValid()
    QgsMapLayerRegistry.instance().addMapLayer(dataLayer)

templateDoc = QDomDocument()

Processing.initialize()

class DwdScriptException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


def fetchLayerByName(name):
    layers = mapRegistry.mapLayersByName(name)
    if len(layers) < 1:
        error = "No layer found with name '%s'" % name
        raise DwdScriptException(error)
    else:
        return layers[0]

def fetchAndFilterDataLayerForDatestring(datestring):
    dataLayerName = DATA_LAYER_FORMAT % datestring[:6]

    dataLayer=fetchLayerByName(dataLayerName)
    # set the actual time and day we want to see
    dataLayer.setSubsetString("date="+datestring)
    return dataLayer

def joinDataLayerWithDisplayLayer(dataLayer, displayLayer):
    # Set up join parameters
    joinObject = QgsVectorJoinInfo()
    joinObject.joinLayerId = dataLayer.id()
    joinObject.joinFieldName = "station_id"
    joinObject.targetFieldName = "Stations_I"
    joinObject.memoryCache = True
    joinObject.prefix=""
    joinObject.setJoinFieldNamesSubset(["TT_10"])
    displayLayer.addJoin(joinObject)
    return displayLayer

def updateDisplayLayerWithDate(datestring):

    dataLayer = fetchAndFilterDataLayerForDatestring(datestring)

    # remove previous joins:
    for vectorJoin in STATIC_DISPLAY_LAYER.vectorJoins():
        STATIC_DISPLAY_LAYER.removeJoin(vectorJoin.joinLayerId)
    # ...and join anew:
    STATIC_DISPLAY_LAYER = joinDataLayerWithDisplayLayer(dataLayer, STATIC_DISPLAY_LAYER)

    # do some refreshing, not shure if necessary in a standalone script.
    STATIC_DISPLAY_LAYER.reload()
    iface.mapCanvas().refreshAllLayers()
    return STATIC_DISPLAY_LAYER

def createDisplayLayerFromStationsWithDate(datestring):

    # prepare the data layer for the requested date:
    dataLayer = fetchAndFilterDataLayerForDatestring(datestring)

    # create an in-memory copy of the stations
    feats = [feat for feat in STATIONS_LAYER.getFeatures()]
    mem_layer = QgsVectorLayer("Point?crs=epsg:32632", "duplicated_layer", "memory")
    mem_layer_data = mem_layer.dataProvider()
    attr = STATIONS_LAYER.dataProvider().fields().toList()
    mem_layer_data.addAttributes(attr)
    mem_layer.updateFields()
    mem_layer_data.addFeatures(feats)
    # add this to the map registry so we can operate with it
    QgsMapLayerRegistry.instance().addMapLayer(mem_layer)

    # join the prepared dataLayer to the copy of the stations
    mem_layer = joinDataLayerWithDisplayLayer(dataLayer, mem_layer)

    # select only stations with valid data points for this date
    selection=processing.runalg('qgis:extractbyexpression', mem_layer,'TT_10 IS NOT NULL AND TT_10 > -999',None)
    # create a voroinoi map from the selected stations
    voronoiResult=processing.runalg('qgis:voronoipolygons', selection["OUTPUT"],20.0,None)

    outputLayer = processing.getObject(voronoiResult["OUTPUT"])
    QgsMapLayerRegistry.instance().addMapLayer(outputLayer)

    if(DO_CLIP):
        outputResult=processing.runalg('qgis:clip',outputLayer,CLIP_LAYER,None)
        #print outputLayer.dataProvider().dataSourceUri()
        #print CLIP_LAYER.dataProvider().dataSourceUri()
        QgsMapLayerRegistry.instance().removeMapLayer(outputLayer)
        outputLayer = processing.getObject(outputResult["OUTPUT"])

    #print outputLayer.featureCount()

    QgsMapLayerRegistry.instance().removeMapLayer(mem_layer)
    outputLayer.loadNamedStyle(VORONOI_LAYERSTYLE)
    QgsMapLayerRegistry.instance().addMapLayer(outputLayer)

    return outputLayer

def updateDateAndExportComposerImageWithDate(date):

    datestring = date.strftime("%Y%m%d%H%M")

    if(DO_DYNAMIC_GENERATION):
        outputlayer = createDisplayLayerFromStationsWithDate(datestring)
    else:
        outputlayer = updateDisplayLayerWithDate(datestring)

    # prepare composition
    mapSettings = QgsMapSettings()
    composition = QgsComposition(mapSettings)
    composition.loadFromTemplate(templateDoc)

    # configure map item:
    composerMap = composition.getComposerMapById(0)
    # zoom to extent if set
    if(ZOOM_TO_SHAPEFILE is not None):
        zoomToLayer=QgsVectorLayer(ZOOM_TO_SHAPEFILE,"ZoomTo","ogr")
        if(zoomToLayer.isValid()):
            composerMap.zoomToExtent(zoomToLayer.extent())
        else:
            raise DwdScriptException("Could not load zoom layer!")
    # make sure current data is rendered
    composerMap.renderModeUpdateCachedImage()

    # configure label with current date
    item = composition.getComposerItemById("Datum")
    item.setText(date.strftime("%d.%m.%Y %H:%M Uhr"))

    # set display layer to be displayed:
    layerset = [ outputlayer.id() ]
    mapSettings.setLayers(layerset)


    #export
    imagepath = RESULT_FOLDER+"image_composer2_"+datestring+".png"
    image = composition.printPageAsRaster(0)
    image.save(imagepath)

    print " image written to '%s'" % imagepath

    if(1):
        QgsMapLayerRegistry.instance().removeMapLayer(outputlayer)
        print "removed"



def preflightChecks():

    global templateDoc

    if not os.path.isfile(COMPOSER_TEMPLATE):
        raise DwdScriptException("Composer template file '%s' does not exist" % COMPOSER_TEMPLATE)

    if not os.path.isdir(RESULT_FOLDER):
        raise DwdScriptException("result folder '%s' does not exist" % RESULT_FOLDER)

    if not os.access(RESULT_FOLDER, os.W_OK):
        raise DwdScriptException("result folder '%s' exists but is not writable" % RESULT_FOLDER)

    # preload template
    templateFile = file(COMPOSER_TEMPLATE)
    templateContent = templateFile.read()
    templateFile.close()

    templateDoc.setContent(templateContent, False)




def main():

    currentDate = datetime.strptime(START+"000000","%Y%m%d%H%M%S")
    maxDate = datetime.strptime(END+"010000","%Y%m%d%H%M%S")

    preflightChecks()

    print "------------------------------------------------------------------------"
    print "JOB Description:"
    print "------------------------------------------------------------------------"
    print " - Generating image sequence spanning             %s - %s" % (currentDate.strftime("%d.%m.%Y %H:%M"), maxDate.strftime("%d.%m.%Y %H:%M"))
    print " - Saving images in                               '%s'" % RESULT_FOLDER
    print " - Script uses Composer Template                  '%s'" % COMPOSER_TEMPLATE
    if(RENDER_LIMIT > 0): print "   ---> Limiting to %d images because RENDER_LIMIT is set" % RENDER_LIMIT
    print "------------------------------------------------------------------------"
    print ""
    print ""

    deltaTime = maxDate-currentDate
    if(deltaTime.days < 0):
        raise DwdScriptException("maxDate earlier than currentDate ?!??")
    estimatedFrameCount = ((deltaTime.days * 3600 + deltaTime.seconds ) / 600 ) * 25

    counter = 0
    try:
        while currentDate <= maxDate:
            counter += 1
            print "[%06d/%06d] generating map for %s" % (counter, estimatedFrameCount, currentDate.strftime("%Y-%m-%d %H:%M"))
            datestring = currentDate.strftime("%Y%m%d%H%M")

            updateDateAndExportComposerImageWithDate(currentDate)

            if (RENDER_LIMIT > 0) & (counter >= RENDER_LIMIT):
                break
            currentDate = currentDate + timedelta(minutes = 10)

        print "script finished writing %d files" % counter
    except KeyboardInterrupt:
        print "Shutdown requested"
    except DwdScriptException as e:
        print e

main()

qgs.exitQgis()
time.sleep(4)
sys.exit()