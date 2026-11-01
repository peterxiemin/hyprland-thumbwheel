# hyprland-thumbwheel

A Hyprland plugin that moves the built-in scrolling layout with a horizontal mouse wheel. It feeds the wheel's axis delta into the same layout movement primitive used by Hyprland's scrolling gesture, so the view moves in small, proportional increments instead of jumping between windows.

This is an experimental community plugin. It is currently built and tested against **Hyprland 0.57.0** (commit `0aa6745f705f2c4b0a5004eb019ef76e5bbdb426`). Hyprland plugins use internal interfaces; other versions may require source changes and a rebuild. An ABI check rejects mismatched builds.

## Behavior

- Unmodified horizontal wheel input pans the focused monitor's regular workspace when it uses the `scrolling` layout. It consumes that input, so applications on that workspace do not receive it.
- Wheel input on other layouts or special workspaces, modified input, input during screen lock, and captured input are left alone. The plugin does not distinguish between individual horizontal-wheel devices.
- Once input stops for 140 ms, focus may follow the column at the center of the view without snapping the layout. There is no synthetic inertia.
- Direction and sensitivity are currently fixed in the source; 15 axis units correspond to 80 logical pixels, with a 400-pixel cap per event.

## Install with hyprpm

The build needs a C++23 compiler, `make`, `pkg-config`, Hyprland development headers and `libeis` development files. Use headers and dependencies matching the running compositor. On systems where `hyprpm` is packaged separately, install it first.

```sh
hyprpm update
hyprpm add https://github.com/peterxiemin/hyprland-thumbwheel
hyprpm enable xiemin-thumbwheel
hyprpm reload
```

Configure your system to reload hyprpm plugins at session start as described in the [Hyprland documentation](https://wiki.hypr.land/hyprland-plugins/using-plugins/). Do not also load another copy manually or bind the unmodified horizontal wheel to layout actions.

## Manual build

```sh
make
hyprctl plugin load "$(pwd)/thumbwheel.so"
hyprctl plugin list
```

To unload, run `hyprctl plugin unload` with the same absolute path used to load it. Manual loads are not persistent unless added to your Hyprland configuration. The Makefile builds to a temporary file and renames it, so rebuilding does not overwrite an already-mapped library. After rebuilding, unload and reload the plugin to use the new binary.

## Validation

On Hyprland 0.57.0, the plugin was loaded in a nested compositor and tested with synthetic full- and half-size horizontal wheel events; movement scaled with input, reversed back to the starting position, and survived unload and workspace-switch cases. It was also checked with synthetic events in one running desktop session. Physical-device feel and other Hyprland versions have not yet been broadly tested.

## License

BSD-3-Clause. The implementation uses Hyprland internal APIs and follows its scrolling-gesture behavior; see [NOTICE](NOTICE) for upstream attribution.
