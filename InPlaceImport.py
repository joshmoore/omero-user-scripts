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
Module documentation
"""

from omero.scripts import client as Client
from omero.scripts import String
from omero.scripts import Bool
from omero.util.import_candidates import as_dictionary
from omero.util.import_candidates import as_stdout
from omero.rtypes import rstring
from path import path


def in_place_import(client, used_files):
    return "NYI"


if __name__ == "__main__":

    client = Client(
        'InPlaceImport.py',
        ('Server-side import which can be used to symlink files into place rather '
         'than copying them'),

        String(
            "Path", optional=False, grouping="1",
            description=("Target path to be passed to the importer. "
                         "This should match what you would pass to bin/omero import -f")),

        Bool(
            "Dry_Run", grouping="2", default=True,
            description=("If this is a dry run, no import will take place. "
                         "Instead a list of importable files will be returned.")),

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
            message = in_place_import(client, used_files)
            client.setOutput("Message", rstring(message))

    finally:
        client.closeSession()
