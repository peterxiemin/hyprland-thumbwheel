#include <chrono>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <algorithm>
#include <optional>

#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/view/window/Window.hpp>
#include <hyprland/src/layout/algorithm/Algorithm.hpp>
#include <hyprland/src/layout/algorithm/tiled/scrolling/ScrollingAlgorithm.hpp>
#include <hyprland/src/layout/space/Space.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/protocols/InputCapture.hpp>
#include <hyprland/src/workspace/HLWorkspace.hpp>

using namespace std::chrono_literals;
namespace {
constexpr float PIXELS_PER_AXIS_UNIT = 80.0f / 15.0f;
constexpr auto GESTURE_IDLE = 140ms;
CHyprSignalListener axisListener;
SP<CEventLoopTimer> finishTimer;
PHLWORKSPACEREF gestureWorkspace;
PHLWINDOWREF startingFocus;
bool gestureActive = false;

Layout::Tiled::CScrollingAlgorithm* scrollingLayout(const PHLWORKSPACE& workspace) {
    if (!workspace || !workspace->space()) return nullptr;
    auto algorithm = workspace->space()->algorithm();
    if (!algorithm || !algorithm->tiledAlgo()) return nullptr;
    return dynamic_cast<Layout::Tiled::CScrollingAlgorithm*>(algorithm->tiledAlgo().get());
}

void finishGesture() {
    if (!gestureActive) return;
    gestureActive = false;
    auto monitor = Desktop::focusState()->monitor();
    auto workspace = gestureWorkspace.lock();
    if (!monitor || !workspace || monitor->m_activeSpecialWorkspace ||
        monitor->m_activeWorkspace != workspace ||
        Desktop::focusState()->window() != startingFocus.lock() ||
        g_pSessionLockManager->isSessionLocked() ||
        (PROTO::inputCapture && PROTO::inputCapture->isCaptured())) return;
    auto layout = scrollingLayout(workspace);
    if (!layout) return;
    auto column = layout->getColumnAtViewportCenter();
    if (!column || column->targetDatas.empty()) return;
    auto target = column->targetDatas.front()->target.lock();
    if (target && target->window())
        Desktop::focusState()->fullWindowFocus(target->window(), Desktop::FOCUS_REASON_FFM);
}

void onAxis(IPointer::SAxisEvent event, Event::SCallbackInfo& info) {
    if (info.cancelled || event.source != WL_POINTER_AXIS_SOURCE_WHEEL ||
        event.axis != WL_POINTER_AXIS_HORIZONTAL_SCROLL || !std::isfinite(event.delta) || event.delta == 0 ||
        g_pSessionLockManager->isSessionLocked() || g_pInputManager->getModsFromAllKBs() != Input::ModifierMask{Input::HL_MODIFIER_NONE} ||
        (PROTO::inputCapture && PROTO::inputCapture->isCaptured())) return;
    auto monitor = Desktop::focusState()->monitor();
    if (!monitor || monitor->m_activeSpecialWorkspace) return;
    auto workspace = monitor->m_activeWorkspace;
    auto layout = scrollingLayout(workspace);
    if (!layout) return;

    if (gestureActive && gestureWorkspace.lock() != workspace) {
        gestureActive = false;
        finishTimer->cancel();
    }
    if (!gestureActive) {
        gestureActive = true;
        gestureWorkspace = workspace;
        startingFocus = Desktop::focusState()->window();
    }

    // Use the same layout movement primitive as Hyprland's scroll_move gesture.
    // Clamp malformed or unusually large events to keep a single event bounded.
    const auto delta = std::clamp(static_cast<float>(event.delta * PIXELS_PER_AXIS_UNIT), -400.0f, 400.0f);
    layout->moveTape(delta);
    info.cancelled = true;
    finishTimer->updateTimeout(GESTURE_IDLE);
    g_pEventLoopManager->scheduleRecalc();
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE) {
    if (std::strcmp(__hyprland_api_get_hash(), __hyprland_api_get_client_hash()) != 0)
        throw std::runtime_error("Hyprland ABI changed; rebuild thumbwheel plugin");
    finishTimer = makeShared<CEventLoopTimer>(std::nullopt, [](SP<CEventLoopTimer>, void*) { finishGesture(); }, nullptr);
    g_pEventLoopManager->addTimer(finishTimer);
    axisListener = Event::bus()->m_events.input.mouse.axis.listen(onAxis);
    return {"xiemin-thumbwheel", "Continuous scrolling layout with horizontal wheel", "xiemin", "0.1"};
}
APICALL EXPORT void PLUGIN_EXIT() {
    axisListener.reset();
    if (finishTimer) {
        finishTimer->cancel();
        g_pEventLoopManager->removeTimer(finishTimer);
        finishTimer.reset();
    }
    gestureActive = false;
}
