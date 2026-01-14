# MVP Completion Plan - Silta GUI Features

**Date**: November 1, 2025  
**Branch**: `feature/gui-features`  
**Current Completion**: ~75%  
**Target**: 100% MVP as defined in functional requirements

---

## Executive Summary

The core infrastructure is solid and functional. Easy-Switch testing (requirement #3) works perfectly. The main gaps are in device classification and comprehensive capability coverage. This plan addresses the remaining 25% to deliver a complete MVP.

---

## Phase 1: Core Device Detection (High Priority)

### Task 1.1: Add HID Device Type Detection

**File**: `silta/mac_hid.py`

**Technical Approach**:

```python
def get_device_type(usage_page: int, usage: int) -> str:
    """
    Determine device type from HID usage page/usage.

    Standard HID Usage Tables (USB HID 1.11):
    - Usage Page 1 (Generic Desktop):
        - Usage 2 = Mouse
        - Usage 6 = Keyboard
        - Usage 4 = Joystick
        - Usage 5 = Game Pad
    - Usage Page 12 (Consumer): Remote controls
    """
    if usage_page == 0x01:  # Generic Desktop
        if usage == 0x02:
            return "mouse"
        elif usage == 0x06:
            return "keyboard"
        elif usage == 0x04:
            return "joystick"
        elif usage == 0x05:
            return "gamepad"
        elif usage == 0x80:  # System Control
            return "system"
    elif usage_page == 0x0C:  # Consumer
        return "remote"
    return "unknown"
```

**Implementation Steps**:

1. Update `_parse_devices()` to extract `DeviceUsagePage` and `DeviceUsage` from IORegistry
2. Add `usage_page` and `usage` fields to `HIDDevice` dataclass
3. Add `device_type` property that calls `get_device_type()`
4. Update `list_hid_devices()` to populate these fields

**Test Data Needed**:

- Check IORegistry output for your MX Master 3 and keyboard
- Run: `ioreg -lw0 -r -c IOHIDDevice | grep -A 10 "MX Master"`

**Estimated Effort**: 2-3 hours

---

### Task 1.2: Add Internal vs External Detection

**File**: `silta/mac_hid.py`

**Technical Approach**:

```python
def is_builtin_device(device: HIDDevice) -> bool:
    """
    Detect if device is internal (built-in to laptop).

    Strategies (in order of reliability):
    1. Check Built property in IORegistry (if available)
    2. Check LocationID patterns (internal devices have specific ranges)
    3. Match against known Apple internal device PIDs
    4. Check transport type (internal often show as "Internal" or specific patterns)
    """
    # Strategy 1: Explicit built property
    if hasattr(device, 'built') and device.built:
        return True

    # Strategy 2: LocationID patterns
    # Internal devices typically have LocationID in specific range
    if device.location_id is not None:
        # MacBook internal devices often have LocationID like 0x14xxx or 0x15xxx
        # This is hardware-specific and may need adjustment
        if 0x14000000 <= device.location_id <= 0x15ffffff:
            return True

    # Strategy 3: Known Apple internal devices
    APPLE_INTERNAL_PIDS = {
        0x0273,  # Internal Keyboard/Trackpad (MacBook Pro)
        0x0274,  # Internal Keyboard/Trackpad (MacBook Air)
        0x0291,  # Internal Keyboard/Trackpad (newer models)
        # Add more as discovered
    }
    if device.vendor_id == 0x05AC:  # Apple
        if device.product_id in APPLE_INTERNAL_PIDS:
            return True
        # Also check product name
        if device.product and "Internal" in device.product:
            return True

    # Strategy 4: Transport hints
    if device.transport:
        if "Internal" in device.transport:
            return True

    return False
```

**Research Required**:

1. Run on your MacBook and capture IORegistry data for internal keyboard/trackpad
2. Document LocationID patterns
3. Build list of Apple internal device PIDs

**Command to gather data**:

```bash
ioreg -lw0 -r -c IOHIDDevice -a | grep -B 5 -A 15 "Apple Internal"
```

**Implementation Steps**:

1. Add `built` field to `HIDDevice` dataclass (Optional[bool])
2. Update `_parse_devices()` to extract this if available
3. Add `is_builtin` property that implements the detection logic
4. Add constant dict `APPLE_INTERNAL_DEVICE_PIDS`

**Estimated Effort**: 3-4 hours (including research)

---

## Phase 2: Capability Matrix Expansion (Medium Priority)

### Task 2.1: Research and Document Device PIDs

**File**: `docs/device-research.md` (new)

**Research Sources**:

1. **Logitech Database**: https://github.com/pwr-Solaar/Solaar/tree/master/lib/logitech_receiver
2. **Linux kernel USB IDs**: https://github.com/torvalds/linux/blob/master/drivers/hid/hid-ids.h
3. **Your own devices**: Run `python main.py capabilities export`
4. **Community**: Check SwitchMX, logiSwitch repos for PIDs

**Target Devices** (20+ total):

- **Mice**: MX Master 3/3S (all variants), MX Master 2S, MX Anywhere 3/3S, MX Ergo, Lift
- **Keyboards**: MX Keys (all variants), MX Keys Mini, MX Mechanical
- **Combos**: MX Keys + MX Master combos (different PIDs)

**Document Format**:

```markdown
| Device      | VID  | PID (BT) | PID (USB) | PID (Unifying) | Easy-Switch | Notes           |
| ----------- | ---- | -------- | --------- | -------------- | ----------- | --------------- |
| MX Master 3 | 046D | B023     | -         | 4082           | Yes         | Mac/PC variants |
```

**Estimated Effort**: 4-5 hours

---

### Task 2.2: Expand \_CAPS Dictionary

**File**: `silta/capabilities.py`

**Implementation**:

```python
_CAPS: Dict[Tuple[int, int], Set[Capability]] = {
    # === LOGITECH MICE ===
    # MX Master 3 (Bluetooth)
    (0x046D, 0xB023): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},
    # MX Master 3 (Unifying)
    (0x046D, 0x4082): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},
    # MX Master 3S (Bluetooth)
    (0x046D, 0xB034): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},

    # MX Master 2S (Bluetooth)
    (0x046D, 0xB019): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},
    # MX Master 2S (Unifying)
    (0x046D, 0x4069): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},

    # MX Anywhere 3 (Bluetooth)
    (0x046D, 0xB027): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, EASY_SWITCH_CONTROL},
    # MX Anywhere 3 (Unifying)
    (0x046D, 0x4092): {EASY_SWITCH, UNIFYING, EASY_SWITCH_CONTROL},

    # ... (continue with 15+ more devices)

    # === LOGITECH KEYBOARDS ===
    # MX Keys (Bluetooth)
    (0x046D, 0xB35B): {EASY_SWITCH, BLUETOOTH, LOW_ENERGY, PER_APP_PROFILES, EASY_SWITCH_CONTROL},
    # MX Keys (Unifying)
    (0x046D, 0x408A): {EASY_SWITCH, UNIFYING, PER_APP_PROFILES, EASY_SWITCH_CONTROL},

    # ... (continue)

    # === RECEIVERS ===
    (0x046D, 0xC52B): {UNIFYING},  # Unifying receiver
    (0x046D, 0xC548): {Capability("bolt", "Logitech Bolt Receiver")},  # Bolt receiver
}
```

**Validation**:

- Each entry must be verified against at least one source
- Test with actual hardware where possible
- Document source in code comments

**Estimated Effort**: 3-4 hours

---

## Phase 3: GUI Enhancements (Medium Priority)

### Task 3.1: Update Menubar Device Display

**File**: `silta/menubar.py`

**Changes Required**:

1. **Group devices by type**:

```python
def _append_devices_grouped(menu, AppKit, devices, controller):
    """Group and display devices by type with icons."""
    keyboards = [d for d in devices if d.device_type == "keyboard"]
    mice = [d for d in devices if d.device_type == "mouse"]
    others = [d for d in devices if d.device_type not in ("keyboard", "mouse")]

    if keyboards:
        menu.addItemWithTitle_action_keyEquivalent_("⌨️  Keyboards:", None, "")
        for dev in keyboards:
            _append_device(menu, AppKit, dev, controller)

    if mice:
        menu.addItem_(AppKit.NSMenuItem.separatorItem())
        menu.addItemWithTitle_action_keyEquivalent_("🖱️  Mice:", None, "")
        for dev in mice:
            _append_device(menu, AppKit, dev, controller)

    if others:
        menu.addItem_(AppKit.NSMenuItem.separatorItem())
        menu.addItemWithTitle_action_keyEquivalent_("Other Devices:", None, "")
        for dev in others:
            _append_device(menu, AppKit, dev, controller)
```

2. **Add internal/external labels**:

```python
def _format_device_title(dev) -> str:
    title = dev.product or f"VID {dev.vendor_id:04X} PID {dev.product_id:04X}"

    # Add location indicator
    if dev.is_builtin:
        title = f"{title} (Internal)"
    else:
        title = f"{title} (External)"

    # Add transport if external
    if not dev.is_builtin and dev.transport:
        title = f"{title} - {dev.transport}"

    return title
```

3. **Update \_append_device() call sites**

**Estimated Effort**: 2-3 hours

---

## Phase 4: Runtime Capability Loading (Low Priority)

### Task 4.1: Implement JSON Loading

**File**: `silta/capabilities.py`

**Implementation**:

```python
_RUNTIME_CAPS: Dict[Tuple[int, int], Set[Capability]] = {}
_CAPS_LOADED = False

def load_capabilities_from_json(path: str) -> None:
    """Load capabilities from external JSON and merge with built-in."""
    global _RUNTIME_CAPS, _CAPS_LOADED

    try:
        data = load_capabilities_json(path)
        # Parse JSON structure and populate _RUNTIME_CAPS
        # Merge with built-in _CAPS
        _CAPS_LOADED = True
    except (OSError, ValueError) as exc:
        LOG.warning(f"Could not load capabilities JSON: {exc}")

def capabilities_for(vendor_id: int, product_id: int) -> List[Capability]:
    """Return capability hints, checking runtime data first."""
    if not _CAPS_LOADED:
        _try_auto_load_capabilities()

    # Check runtime caps first (user-provided), then built-in
    key = (vendor_id, product_id)
    caps = _RUNTIME_CAPS.get(key) or _CAPS.get(key, set())
    return sorted(caps, key=lambda c: c.key)

def _try_auto_load_capabilities() -> None:
    """Auto-load docs/capabilities.json if available."""
    default_path = os.path.join(os.getcwd(), "docs", "capabilities.json")
    if os.path.exists(default_path):
        load_capabilities_from_json(default_path)
```

**Estimated Effort**: 2-3 hours

---

### Task 4.2: Generate Initial capabilities.json

**File**: `docs/capabilities.json`

**Approach**:

1. Run export with your currently connected devices
2. Manually add researched devices from Task 2.1
3. Add schema documentation in header comments

**JSON Structure**:

```json
{
	"version": "1.0",
	"last_updated": "2025-11-01",
	"vendors": {
		"046D": {
			"name": "Logitech",
			"products": {
				"MX Master 3": {
					"pids": ["B023", "4082"],
					"capabilities": ["easy_switch", "bluetooth", "ble", "unifying", "easy_switch_control"],
					"notes": "B023=Bluetooth, 4082=Unifying"
				}
			}
		}
	}
}
```

**Estimated Effort**: 1-2 hours

---

## Phase 5: Testing & Documentation (High Priority)

### Task 5.1: Add Unit Tests

**File**: `tests/test_device_types.py` (new)

**Test Cases**:

```python
def test_get_device_type_mouse():
    assert get_device_type(0x01, 0x02) == "mouse"

def test_get_device_type_keyboard():
    assert get_device_type(0x01, 0x06) == "keyboard"

def test_is_builtin_apple_internal():
    dev = HIDDevice(vendor_id=0x05AC, product_id=0x0273, ...)
    assert is_builtin_device(dev) is True

def test_is_builtin_external_logitech():
    dev = HIDDevice(vendor_id=0x046D, product_id=0xB023, ...)
    assert is_builtin_device(dev) is False
```

**Run tests**: `pytest -v tests/test_device_types.py`

**Estimated Effort**: 2-3 hours

---

### Task 5.2: End-to-End Testing

**Checklist**:

```markdown
## GUI Launch

- [ ] `python main.py gui` starts without errors
- [ ] Menubar icon appears in status bar
- [ ] Menu opens on click

## Device Display

- [ ] Hostname displays correctly
- [ ] Display info shows all connected monitors
- [ ] Internal display marked as such
- [ ] External display marked as such
- [ ] Refresh rate shown correctly

## Device Enumeration

- [ ] Mouse devices listed under "🖱️ Mice"
- [ ] Keyboard devices listed under "⌨️ Keyboards"
- [ ] Internal/External labels correct
- [ ] Capability hints accurate

## Easy-Switch Testing

- [ ] "Test Easy-Switch" buttons appear for capable devices
- [ ] Slot 1 button switches correctly
- [ ] Slot 2 button switches correctly
- [ ] Slot 3 button switches correctly
- [ ] Feedback message shows success/failure

## Export Functionality

- [ ] "Export capabilities JSON" creates file
- [ ] File contains current devices
- [ ] JSON is valid and well-formatted
```

**Test with**: MX Master 3 (or your Logitech device) + MacBook internal keyboard/trackpad

**Estimated Effort**: 1-2 hours

---

### Task 5.3: Update Documentation

**Files**: `README.md`, `docs/gui-mvp-plan.md`

**README Updates**:

```markdown
## Current Status

### ✅ Implemented Features (MVP Complete)

1. **GUI Menubar Application** (macOS)

   - Mac hostname display
   - Display enumeration with specs (resolution, refresh rate, scale)
   - Device enumeration (keyboards, mice) with type detection
   - Internal vs external device indicators
   - Mouse speed display (read-only)
   - Easy-Switch testing controls
   - Capability hints for supported devices

2. **Device Capabilities Matrix**

   - 25+ Logitech devices supported
   - Easy-Switch detection and control
   - Both Bluetooth and USB receiver support
   - JSON export/import for extensibility

3. **Easy-Switch Control** (MVP Goal ✅)
   - CLI: `python main.py capabilities switch --slot N`
   - GUI: Interactive slot switching buttons
   - Supports MX Master 3/3S, MX Keys, and more
   - Multi-backend fallback (hidutil → hidapi → IOKit)

### 📋 Planned Features (Post-MVP)

- **Easy-Switch Listener**: Auto-detect button presses (INPUT reports)
- **Flow Client Integration**: Auto-connect on Easy-Switch press
- **App Store Build**: PyObjC IOKit enumerator (no subprocesses)
- **Monitor DDC/CI**: Auto-switch display inputs
```

**gui-mvp-plan.md Updates**:

- Mark all Phase 1 tasks as complete
- Update HID capabilities matrix status
- Document testing results

**Estimated Effort**: 1 hour

---

## Timeline & Dependencies

```
Week 1 (High Priority - Can be done in parallel)
├─ Day 1-2: Task 1.1 (Device Type Detection)
├─ Day 1-2: Task 2.1 (PID Research) ← Independent
└─ Day 2-3: Task 1.2 (Internal Detection) ← Needs hardware testing

Week 2 (Medium Priority - Sequential)
├─ Day 1: Task 2.2 (Expand _CAPS) ← Depends on Task 2.1
├─ Day 2: Task 3.1 (Update GUI) ← Depends on Task 1.1, 1.2
└─ Day 3: Task 4.1, 4.2 (JSON Loading) ← Independent

Week 3 (Testing & Polish)
├─ Day 1: Task 5.1 (Unit Tests)
├─ Day 2: Task 5.2 (E2E Testing)
├─ Day 3: Task 5.3 (Documentation)
└─ Day 3: Task 9 (Error Handling) ← Quick win
```

**Total Estimated Effort**: 20-25 hours across 2-3 weeks

---

## Success Criteria

The MVP is complete when:

✅ **Functional Requirements Met**:

1. GUI displays PC name, connected devices, displays, and mouse speed
2. Devices are categorized by type (mouse/keyboard) with icons
3. Internal vs external devices are clearly indicated
4. Capabilities matrix covers 20+ devices
5. Easy-Switch testing works via GUI for all supported devices

✅ **Quality Gates**:

- All unit tests pass
- E2E testing checklist 100% complete
- No crashes or errors on launch
- Documentation accurate and up-to-date
- Code follows existing patterns

✅ **Deliverable**:

- Branch `feature/gui-features` ready to merge to `main`
- README reflects actual implementation
- Screenshots/demo available for users

---

## Risk Mitigation

| Risk                                     | Mitigation                                                        |
| ---------------------------------------- | ----------------------------------------------------------------- |
| **Internal device detection unreliable** | Implement multiple detection strategies with fallbacks            |
| **Limited PID coverage**                 | Start with known devices, add contribution guide for users        |
| **GUI crashes with missing deps**        | Add try/except with helpful messages (Task 9)                     |
| **Hardware unavailable for testing**     | Use mock data, document which features need validation            |
| **Time constraints**                     | Prioritize Tasks 1.1, 1.2, 3.1 - these deliver user-visible value |

---

## Next Immediate Actions

**If starting now**, begin with:

1. **Task 1.1** (Device Type Detection) - Highest impact, foundational
2. **Task 2.1** (PID Research) - Can be done in parallel, low risk
3. **Task 5.1** (Unit Tests) - Set up test scaffolding early

**First commit**: Device type detection with tests
**Second commit**: Internal/external detection
**Third commit**: GUI updates to show new data
**Fourth commit**: Expanded capabilities matrix

---

## Questions for Clarification

Before starting, confirm:

1. Do you have access to both internal (MacBook) and external devices for testing?
2. Which Logitech devices do you own? (helps prioritize PIDs)
3. Should we prioritize breadth (many devices) or depth (perfect detection)?
4. Are there specific edge cases you've encountered that need handling?
