#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <wayland-client.h>
#include "virtual-pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *reg, uint32_t name, const char *interface, uint32_t version) {
    (void)data; (void)version;
    if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name))
        manager = wl_registry_bind(reg, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void removed(void *data, struct wl_registry *reg, uint32_t name) { (void)data; (void)reg; (void)name; }
static const struct wl_registry_listener listener = {global, removed};
int main(int argc, char **argv) {
    if (argc < 3 || argc > 5) return 2;
    struct wl_display *d = wl_display_connect(NULL);
    if (!d) return 3;
    struct wl_registry *r = wl_display_get_registry(d);
    wl_registry_add_listener(r, &listener, NULL);
    wl_display_roundtrip(d);
    if (!manager) { fputs("virtual pointer unavailable\n", stderr); return 4; }
    struct zwlr_virtual_pointer_v1 *p = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, NULL);
    wl_display_roundtrip(d);
    struct timespec ready = {.tv_nsec = 200000000}; nanosleep(&ready, NULL);
    int direction = atoi(argv[1]), count = atoi(argv[2]);
    uint32_t axis = argc > 4 && !strcmp(argv[4], "vertical") ? WL_POINTER_AXIS_VERTICAL_SCROLL : WL_POINTER_AXIS_HORIZONTAL_SCROLL;
    for (int i=0; i<count; i++) {
        struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
        uint32_t ms = now.tv_sec * 1000u + now.tv_nsec / 1000000;
        zwlr_virtual_pointer_v1_axis_discrete(p, ms, axis, wl_fixed_from_double(direction * (argc > 3 ? atof(argv[3]) : 15)), direction);
        zwlr_virtual_pointer_v1_axis_source(p, WL_POINTER_AXIS_SOURCE_WHEEL);
        zwlr_virtual_pointer_v1_frame(p);
        wl_display_flush(d);
        struct timespec pause = {.tv_nsec = 25000000}; nanosleep(&pause, NULL);
    }
    wl_display_roundtrip(d);
    zwlr_virtual_pointer_v1_destroy(p);
    zwlr_virtual_pointer_manager_v1_destroy(manager);
    wl_display_disconnect(d);
    return 0;
}
