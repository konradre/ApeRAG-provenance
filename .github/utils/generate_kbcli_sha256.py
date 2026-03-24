#!/usr/bin/env python3
# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -*- coding:utf-8 -*-

# generate kbcli sha256 notes
# 1. open each *.sha256.txt in target direct
# 2. get the contain of the file
# 3. render the template

import os
import sys
from datetime import date
from string import Template

release_note_template_path = "docs/release_notes/template.md"

def main(argv: list[str]) -> None:
    """
    :param: the kbcli version
    :param: the sha256 files direct
    :return None
    """
    kbcli_version = argv[1]
    sha256_direct = argv[2]
    release_note_template_path = "docs/release_notes/kbcli_template.md"
    release_note_path = f"docs/release_notes/{kbcli_version}/kbcli.md"

    template = ""
    try:
        with open(release_note_template_path, "r") as file:
            template = file.read()
    except FileNotFoundError:
        print(f"template {release_note_template_path} not found, IGNORED")

    with open(release_note_path,'a') as f_dest:
        f_dest.write(Template(template).safe_substitute(
            kbcli_version = kbcli_version[1:],
            today = date.today().strftime("%Y-%m-%d"),
        ))
        for file in os.listdir(sha256_direct):
            with open(os.path.join(sha256_direct, file),"r") as f:
                f_dest.write(f.read())
                f_dest.write('\n')
    print("Done")

if __name__ == "__main__":
    main(sys.argv)