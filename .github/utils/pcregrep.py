#!/usr/bin/env python
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
import argparse
import os
import re

parser = argparse.ArgumentParser(description='pcregrep checks Chinese characters')
parser.add_argument('--source', '-s', help='pcregrep source file path', default="pcregrep.out")
parser.add_argument('--filter', '-f', help='push incremental file path', default="")

args = parser.parse_args()
source_file_path = args.source
filter_file_path = args.filter


# Check only incremental files
def pcregrep_Chinese(file_path, filter_path):
    check_pass = True
    # Check for incremental files
    if not filter_path:
        print('incremental files not found!')
        return None

    # Check for pcregrep file
    if not os.path.isfile(file_path):
        print(file_path + ' not found!')
        return None

    filter_paths = filter_path.splitlines()
    pattern = '[\u4e00-\u9fa5]'
    pat = re.compile(pattern)

    with open(file_path, 'rb') as doc:
        lines = doc.readlines()
        for line in lines:
            try:
                line = line.decode(encoding="utf-8")
                # There are Chinese characters
                if pat.findall(line):
                    for path in filter_paths:
                        # Matching incremental files
                        if path and path + ":" in line:
                            print(line[:-1])
                            check_pass = False
                            break
            except UnicodeDecodeError:
                # Ignore coding error messages
                continue

    if check_pass:
        print('pcregrep check success!')
    else:
        raise Exception("The submitted files contains Chinese characters!")


if __name__ == '__main__':

    pcregrep_Chinese(source_file_path, filter_file_path)
