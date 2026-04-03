# Ghidra setup notes

This project can call Ghidra headless, but raw BIN import settings are firmware-specific.

## Minimum fields to set

In `settings.json`:

```json
{
  "ghidra": {
    "enabled": true,
    "install_dir": "/path/to/ghidra",
    "processor": "tricore:BE:32:default",
    "compiler_spec": "default",
    "extra_import_args": []
  }
}
```

## Why `extra_import_args` exists

Different ECUs and Ghidra versions may need different import arguments for raw binaries.

Examples you may want to try depending on target:

- loader selection for raw binary import
- base-address import flags
- language-specific import flags

The wrapper passes these values through untouched so you can keep a family-specific config.

## Suggested workflow

1. import one sample manually in Ghidra GUI first
2. note the exact processor / compiler / loader settings that work
3. copy those into the JSON config
4. switch to headless runs for batch use
