#!/usr/bin/env bash
# Applies the per-update state logging override to a TrickHLA clone, then the
# simulation must be rebuilt with trick-CP.
#
# The script copies LoggingSpaceFOM.hh into the TrickHLA include tree and
# switches the reference frame and physical entity packings in the two
# S_modules simulation object definitions to the logging subclasses. The
# original files are kept next to the patched ones with a .orig suffix.
set -euo pipefail

trickhla=${1:-${TRICKHLA_HOME:-}}
if [ -z "$trickhla" ] || [ ! -d "$trickhla" ]; then
    echo "usage: apply-logging-override.sh <trickhla-root>" >&2
    exit 2
fi

here=$(cd "$(dirname "$0")" && pwd)
header="$trickhla/include/SpaceFOM/LoggingSpaceFOM.hh"
ref_sm="$trickhla/S_modules/SpaceFOM/RefFrame.sm"
entity_sm="$trickhla/S_modules/SpaceFOM/PhysicalEntity.sm"

cp "$here/LoggingSpaceFOM.hh" "$header"

entity_py="$trickhla/TrickHLA_data/SpaceFOM/SpaceFOMPhysicalEntityObject.py"

python3 - "$ref_sm" "$entity_sm" "$entity_py" <<'EOF'
import pathlib
import sys

ref_path = pathlib.Path(sys.argv[1])
entity_path = pathlib.Path(sys.argv[2])
entity_py_path = pathlib.Path(sys.argv[3])

ref = ref_path.read_text()
if 'LoggingRefFrameState frame_packing;' in ref:
    print('RefFrame.sm already patched')
else:
    ref_path.with_suffix('.sm.orig').write_text(ref)
    include_anchor = '#include "THLAObjectBase.sm"'
    assert include_anchor in ref, 'RefFrame.sm anchor missing'
    ref = ref.replace(
        include_anchor,
        '// Per-update state logging override.\n##include "SpaceFOM/LoggingSpaceFOM.hh"\n\n' + include_anchor,
        1)
    member = '   SpaceFOM::RefFrameState frame_packing;'
    assert member in ref, 'RefFrame.sm packing member missing'
    ref = ref.replace(member, '   LoggingRefFrameState frame_packing;', 1)
    ref_path.write_text(ref)
    print('patched RefFrame.sm')

entity = entity_path.read_text()
if 'LoggingPhysicalEntity entity_packing;' in entity:
    print('PhysicalEntity.sm already patched')
else:
    entity_path.with_suffix('.sm.orig').write_text(entity)
    include_anchor = '#include "THLAObjectBase.sm"'
    assert include_anchor in entity, 'PhysicalEntity.sm anchor missing'
    entity = entity.replace(
        include_anchor,
        '// Per-update state logging override.\n##include "SpaceFOM/LoggingSpaceFOM.hh"\n\n' + include_anchor,
        1)
    member = '   SpaceFOM::PhysicalEntity entity_packing;'
    assert member in entity, 'PhysicalEntity.sm packing member missing'
    entity = entity.replace(member, '   LoggingPhysicalEntity entity_packing;', 1)
    entity_path.write_text(entity)
    print('patched PhysicalEntity.sm')

entity_py = entity_py_path.read_text()
if 'mirroring the reference frame configuration' in entity_py:
    print('SpaceFOMPhysicalEntityObject.py already patched')
else:
    entity_py_path.with_suffix('.py.orig').write_text(entity_py)
    anchor = 'thla_thread_IDs           = entity_thread_IDs )'
    assert anchor in entity_py, 'SpaceFOMPhysicalEntityObject.py anchor missing'
    insert = (anchor + '\n\n'
              '      # Set the entity instance name for subscribed entities too,\n'
              '      # mirroring the reference frame configuration, so the packing\n'
              '      # initialization check passes before the first update arrives.\n'
              '      entity_S_define_instance.set_name( entity_instance_name )')
    entity_py = entity_py.replace(anchor, insert, 1)
    entity_py_path.write_text(entity_py)
    print('patched SpaceFOMPhysicalEntityObject.py')
EOF

echo "logging override applied to $trickhla"
