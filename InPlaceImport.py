#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2013 Glencoe Software, Inc. All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
OMERO.script to allow importing-vi-symlink on the server-side
"""

import omero
import omero.all

from omero.constants.namespaces import NSLOGFILE
from omero.callbacks import CmdCallbackI
from omero.cmd import ERR
from omero.grid import ImportResponse
from omero.grid import ImportSettings
from omero.grid import ManagedRepositoryPrx
from omero.model import ChecksumAlgorithmI
from omero.model import FilesetI
from omero.model import FilesetEntryI
from omero.model import FilesetVersionInfoI
from omero.model import UploadJobI
from omero.scripts import client as Client
from omero.scripts import String
from omero.scripts import Bool
from omero.util.import_candidates import as_dictionary
from omero.util.import_candidates import as_stdout
from omero.rtypes import rbool
from omero.rtypes import rstring
from omero_sys_ParametersI import ParametersI
from omero_version import omero_version
from path import path
from sys import stderr
from zlib import crc32


class CRC32(object):
    ("http://stackoverflow.com/questions/1742866/"
     "compute-crc-of-file-in-python?rq=1")
    name = 'crc32'
    digest_size = 4
    block_size = 1

    @staticmethod
    def read(filename, block_size=2**20):
        chk = CRC32()
        f = open(filename, "rb")
        try:
            while True:
                data = f.read(block_size)
                if not data:
                    break
                chk.update(data)
            return chk.digest()
        finally:
            f.close()

    def __init__(self, arg=''):
        self.__digest = 0
        self.update(arg)

    def copy(self):
        copy = super(self.__class__, self).__new__(self.__class__)
        copy.__digest = self.__digest
        return copy

    def digest(self):
        return self.__digest

    def hexdigest(self):
        return '{:08x}'.format(self.__digest)

    def update(self, arg):
        self.__digest = crc32(arg, self.__digest) & 0xffffffff


class InPlaceImporter(object):
    """
    Class largely copied from ome.formats.importer.ImportLibrary
    """

    def __init__(self, client, used_files):
        assert len(used_files) == 1
        self.client = client
        self.used_files = used_files
        self.srcFiles = self.used_files.values()[0]
        self.category = client.getCategory()
        self.settings = ImportSettings()
        self.fs = FilesetI()
        self.repo = self.lookup_managed_repository()

    def create_import(self):
        self.settings.doThumbnail = rbool(True)
        self.settings.userSpecifiedTarget = None
        self.settings.userSpecifiedName = None
        self.settings.userSpecifiedDescription = None
        self.settings.userSpecifiedAnnotationList = None
        self.settings.userSpecifiedPixels = None
        for srcFile in self.srcFiles:
            entry = FilesetEntryI()
            entry.setClientPath(rstring(str(srcFile)))
            self.fs.addFilesetEntry(entry)
        info = FilesetVersionInfoI()
        info.setBioformatsReader(rstring("TBD"))
        info.setBioformatsVersion(rstring("TBD"))
        info.setOmeroVersion(rstring(omero_version))
        info.setOsArchitecture(rstring("TBD"))
        info.setOsName(rstring("TBD"))
        info.setOsVersion(rstring("TBD"))
        info.setLocale(rstring("TBD"))
        upload = UploadJobI()
        upload.setVersionInfo(info)
        self.fs.linkJob(upload)

        # Using a week checksum to speed things up
        self.settings.checksumAlgorithm = ChecksumAlgorithmI()
        self.settings.checksumAlgorithm.value = rstring("CRC-32")
        return self.repo.importFileset(self.fs, self.settings)

    def lookup_managed_repository(self):
        sf = self.client.sf
        map = sf.sharedResources().repositories()
        for i, proxy in enumerate(map.proxies):
            if proxy is not None:
                rv = ManagedRepositoryPrx.checkedCast(proxy)
                if rv is not None:
                    return rv
        return None

    def symlink_file(self, filename):
        print file

    def run(self):
        self.proc = self.create_import()
        self.handle = None
        self.checksums = list()

        print >>stderr, "FILESET_SYMLINK_START"

        for i, srcFile in enumerate(self.srcFiles):
            self.checksums.append(str(CRC32.read(srcFile)))
            self.symlink_file(srcFile)

        try:
            self.handle = self.proc.verifyUpload(self.checksums)
        except omero.ChecksumValidationException, cve:
            raise cve
        finally:
            print >>stderr, "FILESET_SYMLINK_END"

        # At this point the import is running, check handle for number of
        # steps.
        self.cb = None
        try:
            self.cb = InPlaceImportCallbackI(self)
            self.cb.loop(60*60, 1000)  # Wait 1 hr per step.
            if self.cb.rsp is None:
                raise Exception("Import failure")
            return self.cb.rsp.pixels
        finally:
            if self.cb is not None:
                self.cb.close(True)  # Allow cb to close handle
            else:
                self.handle.close()


class InPlaceImportCallbackI(CmdCallbackI):

    def __init__(self, inplace_importer):
        self.inplace_importer = inplace_importer
        self.rsp = None
        CmdCallbackI.__init__(
            self,
            inplace_importer.client,
            inplace_importer.handle)
        self.logFileId = self.loadLogFile()

    def loadLogFile(self):
        req = self.handle.getRequest()
        fsId = req.activity.getParent().getId().getValue()
        metadataService = self.inplace_importer.client.sf.getMetadataService()
        nsToInclude = [NSLOGFILE]
        nsToExclude = []
        rootIds = [fsId]
        param = ParametersI()
        ofId = None
        try:
            annotationMap = metadataService.loadSpecifiedAnnotationsLinkedTo(
                "FileAnnotation", nsToInclude, nsToExclude,
                "Fileset", rootIds, param)
            if fsId in annotationMap:
                annotations = annotationMap.get(fsId)
                if annotations:
                    fa = annotations.get[0]
                    ofId = fa.getFile().getId().getValue()
        except omero.ServerError:
            ofId = None

        return ofId

    def step(self, step, total, current=None):
        if step == 1:
            msg = "METADATA_IMPORTED"
        elif step == 2:
            msg = "PIXELDATA_PROCESSED"
        elif step == 3:
            msg = "THUMBNAILS_GENERATED"
        elif step == 4:
            msg = "METADATA_PROCESSED"
        elif step == 5:
            msg = "OBJECTS_RETURNED"
        elif step == 2:
            msg = "PIXELDATA_PROCESSED"
        print >>stderr, msg
        self.client.setOutput("Message", rstring(msg))

    def onFinished(self, rsp, status, current=None):
        # TBD waitOnInitialization(); # Need non-null container
        if isinstance(rsp, ERR):
            raise Exception(
                ("Failure response on import!\n"
                 "Category: %s\n"
                 "Name: %s\n"
                 "Parameters: %s\n") %
                (rsp.category, rsp.name, rsp.parameters))
        elif isinstance(rsp, ImportResponse):
            if self.rsp is None:
                # Only respond once.
                self.rsp = rsp
        else:
            raise Exception("Unknown response: " + rsp)
        self.onFinishedDone()


if __name__ == "__main__":

    client = Client(
        'InPlaceImport.py',
        ('Server-side import which can be used '
         'to symlink files into place rather '
         'than copying them'),

        String(
            "Path", optional=False, grouping="1",
            description=("Target path to be passed to the importer. "
                         "This should match what you would pass to "
                         "bin/omero import -f")),

        Bool(
            "Dry_Run", grouping="2", default=True,
            description=("If this is a dry run, no import will take place. "
                         "Instead a list of importable files will be "
                         "returned.")),

        version="5.0.0",
        authors=["Josh Moore", "OME Team"],
        institutions=["University of Dundee"],
        contact="ome-users@lists.openmicroscopy.org.uk",
    )

    try:
        script_params = {}
        for key in client.getInputKeys():
            if client.getInput(key):
                script_params[key] = client.getInput(key, unwrap=True)

        # Wrapping with path due to a bug in import_candidates.py
        target_path = path(script_params["Path"])

        if script_params["Dry_Run"]:
            as_stdout(target_path)
            client.setOutput("Message", rstring("Dry-run: ok"))
        else:
            used_files = as_dictionary(path(script_params["Path"]))
            if len(used_files) == 0:
                msg = "No file found"
                client.setOutput("Message", rstring(msg))
                raise Exception(msg)
            elif len(used_files) > 1:
                msg = "Too many files found! (%s)" % len(used_files)
                client.setOutput("Message", rstring(msg))
                raise Exception(msg)
            else:
                importer = InPlaceImporter(client, used_files)
                importer.run()
                client.setOutput("Message", rstring("Import: ok"))

    finally:
        client.closeSession()
