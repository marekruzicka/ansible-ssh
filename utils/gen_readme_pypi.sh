#!/bin/bash
# Generate README_pypi.md by removing the Installation/shell section from README.md
awk 'BEGIN{p=1} /^### shell/{p=0} /^### pip/{p=1} p' README.md > README_pypi.md
