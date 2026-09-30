// Checks the federates' saved-state encodings without an RTI: every state decodes and re-encodes to the same bytes,
// frames received after the save are set aside for comparison, and truncated or extended states are refused.
#define main spacefom_publisher_main
#include "../../native/spacefom/publisher.cpp"
#undef main
#define main spacefom_observer_main
#include "../../native/spacefom/observer.cpp"
#undef main

namespace {
int failures = 0;
void check(bool condition, const std::string& what) { std::cout << (condition ? "pass " : "FAIL ") << what << std::endl; if (!condition) ++failures; }
template<class F> bool refuses(F action) { try { action(); return false; } catch (const std::exception&) { return true; } }

// Fills an observer as if it had received frames 0..last of the recording.
void receive(Observer& observer, const Bytes& source, const Header& header, size_t frameOffset, int32_t last) {
    const size_t recordSize = 40 + (header.bodies.size() + 1) * stateBytes;
    observer.header = header; observer.metadata = observer.rootSeen = observer.entitySeen = true;
    observer.epoch = little<double>(source.data() + frameOffset + 40 + 104);
    for (const Body& body : header.bodies) observer.bodyStatic.insert("body_" + body.id);
    for (int32_t tick = 0; tick <= last; ++tick) {
        const size_t offset = frameOffset + static_cast<size_t>(tick) * recordSize;
        ReceivedFrame& frame = observer.frames[tick]; frame.tag = Bytes(source.begin() + offset, source.begin() + offset + 40);
        for (size_t j = 0; j <= header.bodies.size(); ++j) {
            const size_t begin = offset + 40 + j * stateBytes;
            frame.states.emplace(j == 0 ? "orbital_vessel" : "body_" + header.bodies[j - 1].id, Bytes(source.begin() + begin, source.begin() + begin + stateBytes));
        }
    }
    observer.currentTick = last; observer.logicalUs = static_cast<int64_t>(last) * stepUs;
    observer.receiveOrderUpdates = header.bodies.size() + 1; observer.timestampedUpdates = static_cast<size_t>(last) * (header.bodies.size() + 1);
    observer.current = 3; observer.next = 3; observer.transitionTime = observer.epoch + static_cast<double>(last) / 64.0;
}
}

int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: state-roundtrip <recording.sf>");
        Bytes source = readFile(argv[1]); Reader reader{source}; Header header = parseHeader(reader);
        const int32_t saved = header.count / 2, later = saved + header.count / 4;

        Observer atSave; receive(atSave, source, header, reader.offset, saved);
        Bytes state = atSave.saveState();
        Observer atRewind; receive(atRewind, source, header, reader.offset, later);
        atRewind.restoreState(state);
        check(atRewind.saveState() == state, "observer state re-encodes to the saved bytes (" + std::to_string(state.size()) + " bytes)");
        check(atRewind.frames.size() == static_cast<size_t>(saved) + 1 && atRewind.currentTick == saved, "observer returns to the saved tick");
        check(atRewind.firstPass.size() == static_cast<size_t>(later - saved) && atRewind.firstPass.begin()->first == saved + 1, "frames after the save are kept for comparison");
        check(refuses([&] { Observer o; o.header = header; o.restoreState(Bytes(state.begin(), state.end() - 1)); }), "truncated observer state refused");
        check(refuses([&] { Observer o; o.header = header; Bytes longer = state; longer.push_back(0); o.restoreState(longer); }), "extended observer state refused");
        check(refuses([&] { Observer o; Header other = header; other.encoded.back() ^= 1; o.header = other; o.restoreState(state); }), "observer state for another recording refused");

        Publisher master; master.currentTick = saved; master.logicalUs = static_cast<int64_t>(saved) * stepUs;
        master.excoCurrent = 3; master.excoNext = 3; master.excoTime = atSave.transitionTime; master.requests = {2};
        Bytes masterState = master.saveState();
        Publisher restored; restored.currentTick = later; restored.restoreState(masterState);
        check(restored.saveState() == masterState && restored.currentTick == saved, "publisher state re-encodes to the saved bytes (" + std::to_string(masterState.size()) + " bytes)");
        check(refuses([&] { Publisher p; p.restoreState(Bytes(masterState.begin(), masterState.end() - 1)); }), "truncated publisher state refused");
    } catch (const std::exception& e) { std::cerr << "failure: " << e.what() << std::endl; return 1; }
    std::cout << (failures == 0 ? "all checks passed" : std::to_string(failures) + " checks failed") << std::endl;
    return failures == 0 ? 0 : 1;
}
