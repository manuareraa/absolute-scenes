#!/usr/bin/env bash
# Regenerate Pydantic and TypeScript types from contracts/schemas.
# CI runs this and fails if the result differs from what is committed.
set -euo pipefail
cd "$(dirname "$0")/.."

out_py=contracts/python/src/chalktalk_contracts/models
rm -rf "$out_py"
uv run datamodel-codegen \
  --input contracts/schemas \
  --input-file-type jsonschema \
  --output "$out_py" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.12 \
  --use-standard-collections \
  --use-union-operator \
  --use-schema-description \
  --use-field-description \
  --disable-timestamp

out_ts=contracts/ts/src/generated
rm -rf "$out_ts"
mkdir -p "$out_ts"
for f in contracts/schemas/*.schema.json; do
  name=$(basename "$f" .schema.json)
  npx --no-install json2ts --cwd contracts/schemas --input "$f" --output "$out_ts/$name.ts" \
    --additionalProperties false --bannerComment "/* Generated from contracts/schemas/$name.schema.json by scripts/gen_contracts.sh. Do not edit. */"
done
