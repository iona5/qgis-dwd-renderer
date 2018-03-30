from ftplib import FTP
import tempfile
import sqlite3
import zipfile
import shutil
import os.path
import csv
import glob

# a class to download data from the DWD CDC server, sort the data by its time reference
# and put it into SQLite files, one for each month.

class DwdData:

    DWD_HOST="ftp-cdc.dwd.de"

    # filename prefix for the resulting SQLite files
    DATABASE_FILE_PREFIX = "dwddata_"
    # name of the table in the SQLite database where the data os put into
    DATABASE_TABLE_NAME = "station_data"

    # how many entries are read before the data is written to the SQLite files
    MAX_VALUES_FLUSH = 2000

    # dictionary to hold different configurations for different data pprovided by DWD
    # the key of each set is used when constructing the object in the parameter "dataset"
    dwdInfo = {
        "TEMP_10MINUTES_RECENT" : {
            "ftpPath" :  "/pub/CDC/observations_germany/climate/10_minutes/air_temperature/recent",
            "fileName" : "10minutenwerte_TU_%05d_akt.zip",
            "fields" : ["PP_10", "TT_10", "TM5_10", "RF_10", "TD_10"] #STATIONS_ID, MESS_DATUM and QN are default
        }
    }

    # databasePath: path where to write the SQLite files
    # dataset: a key from dwdInfo, selects the dataset to download and process
    def __init__(self, databasePath, dataset):
        self.databasePath = databasePath
        self.selectedDataset = dataset
        self.downloadPath = tempfile.mkdtemp()
        self.unpackPath = tempfile.mkdtemp()
        self.sqliteConnections = {}
        self.ftpConnection = None
        self.downloadedFiles = []
        self.unpackedFiles = []


    def getFtpPath(self):
        return DwdData.dwdInfo[self.selectedDataset]["ftpPath"]

    def checkPreconditions(self):
        files = glob.glob(self.databasePath + DwdData.DATABASE_FILE_PREFIX+"*")
        countExistingFiles = len(files)

        if countExistingFiles > 0:
            shouldContinue = raw_input(
                "directory %s already contains %d files with prefix '%s'\n files will be removed, continue [Y/n]? "
                    % (self.databasePath, countExistingFiles, DwdData.DATABASE_FILE_PREFIX)
                ).strip()
            if (len(shouldContinue) == 0) or (shouldContinue.lower() == 'y'):
                for f in files:
                    print "removing file '%s' ..." % f
                    os.remove(f)
            else:
                sys.exit(1)

    def login(self):
        self.ftpConnection = FTP(DwdData.DWD_HOST)
        self.ftpConnection.login()

    def logout(self):
        self.ftpConnection.quit()
        self.ftpConnection = None

    def ftpRetrieveDataList(self):

        dwdFileList = []
        def callbackFileList(line):
            if line.rsplit(".")[-1] != "txt":
                dwdFileList.append(line)

        self.ftpConnection.cwd(self.getFtpPath())
        self.ftpConnection.retrlines("NLST",callbackFileList)

        return dwdFileList

    def downloadFiles(self):
        fileList = self.ftpRetrieveDataList()
        self.ftpConnection.cwd(self.getFtpPath())

        self.downloadedFiles = []

        i=0

        for file in fileList:
            i += 1
            print ("downloading file "+file+" ... (%d/%d)" % (i, len(fileList))),
            self.ftpConnection.retrbinary("RETR "+file, open(self.downloadPath+"/"+file, 'wb').write)
            print "done"
            self.downloadedFiles.append(self.downloadPath+"/"+file)

            if(i > 10):
                break

    def unpackFiles(self):
        if(len(self.downloadedFiles) < 1):
            raise StandardError("now files downloaded yet, exec downloadFiles() or set downloadedFiles")

        self.unpackedFiles = []
        i=0
        for file in self.downloadedFiles:
            i += 1
            print ("unpacking '%s' (%d/%d) ... " % (file, i, len(self.downloadedFiles))),
            with zipfile.ZipFile(file, "r") as archive:
                # find files archived in zip file:
                infoList = archive.infolist()
                if len(infoList) != 1:
                    print
                    print " -> file '%s' contains %d files, expected 1, skipping" % (file, len(self.downloadedFiles))
                    continue

                # take only first file and extract it:
                fileInfo = infoList[0]
                print ("'%s' (%d bytes) " % (fileInfo.filename, fileInfo.file_size)),
                extractedFile = archive.extract(fileInfo, self.unpackPath)
                print "done"
                self.unpackedFiles.append(extractedFile)

    def getDatabaseConnectionForMonth(self, year, month):
        connectionName = "c"+year+month
        if connectionName not in self.sqliteConnections:
            filename = self.databasePath + DwdData.DATABASE_FILE_PREFIX + year + month + ".sqlite"
            print "creating new database file '%s' ... " % filename
            connection = sqlite3.connect(filename)
            cursor = connection.cursor()

            sqliteTableCreateCommand = "CREATE TABLE '" + DwdData.DATABASE_TABLE_NAME +  "' ("
            fieldsSql = ["station_id", "date", "QN"]
            for field in DwdData.dwdInfo[self.selectedDataset]["fields"]:
                fieldsSql.append("'" + field + "' float NOT NULL")

            sqliteTableCreateCommand += ', '.join(fieldsSql)
            sqliteTableCreateCommand += ");"

            try:
                cursor.execute(sqliteTableCreateCommand)
                #cursor.execute("CREATE TABLE '" + DB_TABLENAME +  "' ('station_id' integer NOT NULL, 'date' datetime NOT NULL, 'QN' integer NOT NULL, 'PP_10' float NOT NULL, 'TT_10' float NOT NULL, 'TM5_10' float NOT NULL, 'RF_10' float NOT NULL, 'TD_10' float NOT NULL);")
            except sqlite3.OperationalError as e:
                print "sqlite error '%s' during creation of database, sqlite database %s already exists ??" % (e.strerror, filename)


            connection.commit()
            cursor.close()
            print "done"
            self.sqliteConnections[connectionName] = connection

        return self.sqliteConnections[connectionName]



    def importFilesIntoSqlite(self):

        if len(self.unpackedFiles) < 1:
            raise StandardError("now files unpacked yet, exec downloadFiles() or set unpackedFiles")

        lengthOfFields = 3 + len(DwdData.dwdInfo[self.selectedDataset]["fields"])

        def flushBuffers():
            for yearMonth, data in monthData.iteritems():
                year = yearMonth[:4]
                month = yearMonth[4:6]
                connection = self.getDatabaseConnectionForMonth(year, month)

                # create the SQL insert command dependant on the count of fields in this dataset
                # similar to "INSERT INTO station_data VALUES (?,?,?,?,?,?,?,?)"
                fieldString = ["?"] * (lengthOfFields)
                valuePlaceholder = ",".join(fieldString)
                insertCommand = "INSERT INTO %s VALUES (%s)" % (DwdData.DATABASE_TABLE_NAME, valuePlaceholder)

                connection.cursor().executemany(insertCommand, data)
                connection.commit()
                monthData[yearMonth] = []

        i = 0
        for dataFile in self.unpackedFiles:
            i += 1
            print "processing file %s (%d/%d)" % (dataFile, i, len(self.unpackedFiles))
            with open(dataFile,"r") as stationFile:
                monthData = {}

                dataFileReader = csv.reader(stationFile, delimiter = ';', skipinitialspace = True)
                counter = 0
                for row in dataFileReader:
                    if (len(row) == lengthOfFields) and not (row[0][:1] == "S"):
                        date = row[1]
                        yearMonth = date[:6]

                        try:
                            monthData[yearMonth]
                        except KeyError:
                            monthData[yearMonth] = []

                        # create the tuple of data with dynamic fields cast to float
                        data = ( int(row[0]), row[1], int(row[2]) )
                        for iField in range(3, lengthOfFields):
                            data = data + ( float(row[iField]), )

                        monthData[yearMonth].append( data )

                        counter += 1
                        if (counter % 100) == 0:
                            print ("processing line %d \r" % counter),

                        if (counter % DwdData.MAX_VALUES_FLUSH) == 0:
                            # flush buffers to sqlite files
                            flushBuffers()

                print ""

                # final flush:
                flushBuffers()

        #close all sqlite connections created during import
        for conn in self.sqliteConnections.itervalues():
            conn.close()

    def execute(self):
        self.checkPreconditions()

        self.login()
        self.downloadFiles()
        self.logout()

        self.unpackFiles()
        self.importFilesIntoSqlite()



    def __del__(self):
        print "removing download folder %s ... " % self.downloadPath
        shutil.rmtree(self.downloadPath)

        print "removing unpack folder %s ... " % self.unpackPath
        shutil.rmtree(self.unpackPath)


        try:
            if self.ftpConnection:
                print "logging out ... "
                self.logout()
        except NameError:
            pass
