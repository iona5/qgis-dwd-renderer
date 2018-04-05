# before importing this module, make sure the PyQgis environment is correctly set up.
# for example:
# Append QGIS Python library to python search path
#sys.path.append(QGIS_PREFIX_PATH + '/python')
#sys.path.append(QGIS_PREFIX_PATH + '/python/plugins')
# Append location of DLLs to current system PATH envrionment variable
#os.environ['PATH'] += ";" + QGIS_PREFIX_PATH + "/bin"
# THIS SEEMS TO WORK!!!
#os.environ['QGIS_PREFIX_PATH'] = QGIS_PREFIX_PATH
# the following is suggested to do, but DOES NOT WORK!!! Setting the prefix path via
# os.environ DOES WORK!
#QgsApplication.setPrefixPath("c:/Program Files/QGIS 2.18/apps/qgis-ltr", False)


import os, sys
from qgis.core import *
import qgis
import os.path
from datetime import datetime
from datetime import timedelta
import time
from PyQt4.QtXml import QDomDocument
from PyQt4.QtCore import QTimer
import processing
from processing.core.Processing import Processing

class QgisDwdException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

def fetchLayerByName(mapRegistry, name):
    layers = mapRegistry.mapLayersByName(name)
    if len(layers) < 1:
        error = "No layer found with name '%s'" % name
        raise QgisDwdException(error)
    else:
        return layers[0]

def joinLayers(joinLayer, joinFieldName, targetLayer, targetFieldName, fieldSubset):
    # Set up join parameters
    joinObject = QgsVectorJoinInfo()
    joinObject.joinLayerId = joinLayer.id()
    joinObject.joinFieldName = joinFieldName
    joinObject.targetFieldName = targetFieldName
    joinObject.memoryCache = True
    joinObject.prefix=""
    joinObject.setJoinFieldNamesSubset(fieldSubset)
    targetLayer.addJoin(joinObject)
    return targetLayer

class QgisDwdRenderer(object):
    def __init__(self, dataFilePath, displayLayerStyleFile,
        composerTemplateFile, resultFolderPath, zoomToLayerFile, useProcessing):
        self.dataFilePath = dataFilePath
        self.displayLayerStyleFile = displayLayerStyleFile
        self.composerTemplateFile = composerTemplateFile
        self.resultFolderPath = resultFolderPath
        self.zoomToLayerFile = zoomToLayerFile

        if not os.path.isdir(self.resultFolderPath):
            raise QgisDwdException("result folder '%s' does not exist" % self.resultFolderPath)
        if not os.access(self.resultFolderPath, os.W_OK):
            raise QgisDwdException("result folder '%s' exists but is not writable" % self.resultFolderPath)

        # load template
        if not os.path.isfile(self.composerTemplateFile):
            raise QgisDwdException("Composer template file '%s' does not exist" % self.composerTemplateFile)
        self.composerTemplate = QDomDocument()
        templateFile = file(composerTemplateFile)
        templateContent = templateFile.read()
        templateFile.close()
        self.composerTemplate.setContent(templateContent, False)

        useGuiLibs = True

        self.QGS = QgsApplication([],useGuiLibs) # 2nd parameter needs to be true in order for processing framework to ... work.
        self.QGS.initQgis()
        self.PROJECT = QgsProject.instance()
        self.MAP_REGISTRY = QgsMapLayerRegistry.instance()
        self.COMPOSER_TEMPLATE_DOCUMENT = QDomDocument()
        if(useProcessing):
            Processing.initialize()

        self.DATA_LAYER_NAME_FORMAT = "%s station_data"

    def fetchAndFilterDataLayerForDatestring(self, datestring):
        dataLayerName = self.DATA_LAYER_NAME_FORMAT % datestring[:6]

        dataLayer=fetchLayerByName(self.MAP_REGISTRY, dataLayerName)
        # set the actual time and day we want to see
        dataLayer.setSubsetString("date="+datestring)
        return dataLayer

    def renderDisplayLayer(self, displayLayer, dateLabelString, imagepath, imageDpi):
        # prepare composition
        mapSettings = QgsMapSettings()
        composition = QgsComposition(mapSettings)
        composition.loadFromTemplate(self.composerTemplate)

        # configure map item:
        composerMap = composition.getComposerMapById(0)

        # zoom to extent if set
        if(self.zoomToLayerFile is not None):
            zoomToLayer=QgsVectorLayer(self.zoomToLayerFile,"ZoomTo","ogr")
            if(zoomToLayer.isValid()):
                composerMap.zoomToExtent(zoomToLayer.extent())
            else:
                raise QgisDwdException("Could not load zoom layer!")


        # make sure current data is rendered
        composerMap.renderModeUpdateCachedImage()

        # configure label with current date
        item = composition.getComposerItemById("Datum")
        item.setText(dateLabelString)

        # set display layer to be displayed:
        layerset = [ displayLayer.id() ]
        mapSettings.setLayers(layerset)

        #export
        image = composition.printPageAsRaster(0, dpi = imageDpi)
        image.save(imagepath)


    def loadDataFiles(self, fromDate, toDate):
        # create the list of months to load:
        monthList = []
        delta = timedelta(days=30) # add a "month"
        while(fromDate < toDate):
            monthList.append(fromDate.strftime("%Y%m"))
            fromDate += delta

        for month in monthList:
            dataLayerName = self.DATA_LAYER_NAME_FORMAT % month
            # check if layer is already loaded:
            layers = self.MAP_REGISTRY.mapLayersByName(dataLayerName)
            if len(layers) < 1:
                dataLayerFile = self.dataFilePath % month
                dataLayer = QgsVectorLayer(dataLayerFile, dataLayerName, "ogr")
                if not dataLayer.isValid():
                    raise QgisDwdException("data layer file '%s' not found" % dataLayerFile )
                self.MAP_REGISTRY.addMapLayer(dataLayer)

    def execute(self, fromDateString, toDateString, renderLimit = 0, useCounterForName = False, imageDpi = 0):
        fromDateTime = datetime.strptime(fromDateString+"000000","%Y%m%d%H%M%S")
        toDateTime = datetime.strptime(toDateString+"000000","%Y%m%d%H%M%S")

        self.loadDataFiles(fromDateTime, toDateTime)

        deltaTime = toDateTime - fromDateTime
        if(deltaTime.days < 0):
            raise QgisDwdException("maxDate earlier than currentDate ?!??")
        estimatedFrameCount = ((deltaTime.days * 86400 + deltaTime.seconds ) / 600 ) + 1

        currentDate = fromDateTime
        counter = 0
        try:
            while currentDate <= toDateTime:
                counter += 1
                print "[%06d/%06d] generating map for %s" % (counter, estimatedFrameCount, currentDate.strftime("%Y-%m-%d %H:%M"))

                dateLabelString = currentDate.strftime("%d.%m.%Y %H:%M Uhr")
                displayLayer = self.prepareDisplayLayer(currentDate)

                if useCounterForName:
                    counterFilename = "%08d" % counter
                else:
                    counterFilename = currentDate.strftime("%Y%m%d%H%M")

                imagepath = os.path.join(self.resultFolderPath,"image_composer2_"+counterFilename+".png")
                self.renderDisplayLayer(displayLayer, dateLabelString, imagepath, imageDpi)
                print "                -> '%s'" % imagepath
                self.MAP_REGISTRY.removeMapLayer(displayLayer)

                if (renderLimit > 0) & (counter >= renderLimit):
                    break
                currentDate = currentDate + timedelta(minutes = 10)

            print "script finished writing %d files" % counter
        except KeyboardInterrupt:
            print "Shutdown requested"
        except QgisDwdException as e:
            print e

    def teardown(self):
        self.QGS.exitQgis()


class StaticQgisDwdRenderer(QgisDwdRenderer):
    def __init__(self, dataFilePath, displayLayerStyleFile,
        composerTemplateFile, resultFolderPath, displayLayerFile, zoomToLayerFile = None ):

        super(StaticQgisDwdRenderer,self).__init__(dataFilePath, displayLayerStyleFile,
            composerTemplateFile, resultFolderPath, zoomToLayerFile, False)
        self.displayLayer = QgsVectorLayer(displayLayerFile, "display layer", "ogr")
        self.displayLayer.loadNamedStyle(self.displayLayerStyleFile)
        self.MAP_REGISTRY.addMapLayer(self.displayLayer)

    def prepareDisplayLayer(self, datetime):
        datestring = datetime.strftime("%Y%m%d%H%M")

        dataLayer = self.fetchAndFilterDataLayerForDatestring(datestring)

        # remove previous joins:
        for vectorJoin in self.displayLayer.vectorJoins():
            self.displayLayer.removeJoin(vectorJoin.joinLayerId)

        # ...and join anew:
        self.displayLayer = joinLayers(dataLayer, "station_id", self.displayLayer, "Stations_I", ["TT_10"])

        # do some refreshing, not sure if necessary in a standalone script.
        #self.displayLayer.reload()
        return self.displayLayer



class DynamicQgisDwdRenderer(QgisDwdRenderer):
    def __init__(self, dataFilePath, displayLayerStyleFile,
        composerTemplateFile, resultFolderPath, stationPointLayerFile, clipLayerFile = None, zoomToLayerFile = None):

        super(DynamicQgisDwdRenderer,self).__init__(
            dataFilePath, displayLayerStyleFile, composerTemplateFile,
            resultFolderPath, zoomToLayerFile, True)

        self.stationsLayer=QgsVectorLayer(stationPointLayerFile, "stations_10min_32632", "ogr")
        self.MAP_REGISTRY.addMapLayer(self.stationsLayer)

        if clipLayerFile is not None:
            self.clipLayer=QgsVectorLayer(clipLayerFile, "clip layer", "ogr")
            self.MAP_REGISTRY.addMapLayer(self.clipLayer)
        else:
            self.clipLayer = None

    def prepareDisplayLayer(self, datetime):
        datestring = datetime.strftime("%Y%m%d%H%M")
        dataLayer = self.fetchAndFilterDataLayerForDatestring(datestring)

        # create an in-memory copy of the stations
        feats = [feat for feat in self.stationsLayer.getFeatures()]
        mem_layer = QgsVectorLayer("Point?crs=epsg:32632", "duplicated_layer", "memory")
        mem_layer_data = mem_layer.dataProvider()
        attr = self.stationsLayer.dataProvider().fields().toList()
        mem_layer_data.addAttributes(attr)
        mem_layer.updateFields()
        mem_layer_data.addFeatures(feats)

        # add this to the map registry so we can operate with it
        self.MAP_REGISTRY.addMapLayer(mem_layer)
        # join the prepared dataLayer to the copy of the stations
        mem_layer = joinLayers(dataLayer, "station_id", mem_layer, "Stations_I", ["TT_10"])

        # select only stations with valid data points for this date
        selection=processing.runalg('qgis:extractbyexpression', mem_layer,'TT_10 IS NOT NULL AND TT_10 > -999',None)
        # create a voroinoi map from the selected stations
        voronoiResult=processing.runalg('qgis:voronoipolygons', selection["OUTPUT"],20.0,None)

        outputLayer = processing.getObject(voronoiResult["OUTPUT"])
        self.MAP_REGISTRY.addMapLayer(outputLayer)

        if(self.clipLayer is not None):
            outputResult=processing.runalg('qgis:clip',outputLayer,self.clipLayer,None)
            #print outputLayer.dataProvider().dataSourceUri()
            #print CLIP_LAYER.dataProvider().dataSourceUri()
            self.MAP_REGISTRY.removeMapLayer(outputLayer)
            outputLayer = processing.getObject(outputResult["OUTPUT"])
            self.MAP_REGISTRY.addMapLayer(outputLayer)

        self.MAP_REGISTRY.removeMapLayer(mem_layer)
        outputLayer.loadNamedStyle(self.displayLayerStyleFile)

        return outputLayer
