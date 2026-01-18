# Build Wheel + Lambda Layer

Build the CD1 Agent wheel package and Lambda layer.

**Usage**: `/build [target]`

**Argument**: $ARGUMENTS

## Instructions

1. **Determine build target**:
   - If `$ARGUMENTS` is empty or "all": run `make build` (wheel + layer)
   - If `$ARGUMENTS` is "wheel": run `make wheel`
   - If `$ARGUMENTS` is "layer": run `make layer`
   - If `$ARGUMENTS` is "layer-full": run `make layer-full`

2. **Execute build**:
   ```bash
   make <target>
   ```

3. **Verify outputs**:
   ```bash
   ls -la dist/
   ```

4. **Report results**:
   - Build target executed
   - Output files created
   - File sizes

## Build Targets

| Target | Description |
|--------|-------------|
| (empty) | Build wheel + basic Lambda layer |
| wheel | Build wheel package only |
| layer | Build basic Lambda layer |
| layer-full | Build Lambda layer with all optional deps |

## Output Format

```
Build Complete: <target>

Outputs:
- dist/cd1_agent-x.x.x-py3-none-any.whl (xxx KB)
- dist/cd1-agent-layer.zip (xxx MB)
```
