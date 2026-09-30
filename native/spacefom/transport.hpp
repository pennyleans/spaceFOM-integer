#pragma once
#include <RTI/RTIambassadorFactory.h>
#include <RTI/RTIambassador.h>
#include <RTI/NullFederateAmbassador.h>
#include <RTI/time/HLAinteger64Time.h>
#include <RTI/time/HLAinteger64Interval.h>
#include <RTI/encoding/BasicDataElements.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace sf {
namespace rti = rti1516e;
using Bytes = std::vector<unsigned char>;
constexpr int64_t stepUs = 15625;
constexpr size_t stateBytes = 112;
const std::string rootName = "SolarSystemBarycentricInertial";
inline void require(bool condition, const std::string& message) { if (!condition) throw std::runtime_error(message); }
inline std::wstring wide(const std::string& value) { return std::wstring(value.begin(), value.end()); }
inline std::string narrow(const std::wstring& value) { std::string result; for(wchar_t c:value) result.push_back(c>=0 && c<128?static_cast<char>(c):'?'); return result; }
inline Bytes bytes(const rti::VariableLengthData& value) {
    const auto* p = static_cast<const unsigned char*>(value.data());
    return value.size() ? Bytes(p, p + value.size()) : Bytes();
}
inline rti::VariableLengthData blob(const Bytes& value) { return rti::VariableLengthData(value.data(), value.size()); }
template<class T> inline T little(const unsigned char* p) {
    static_assert(sizeof(T) == 2 || sizeof(T) == 4 || sizeof(T) == 8, "wire scalar width");
    T v; std::memcpy(&v, p, sizeof(T)); return v;
}
template<class T> inline Bytes scalar(T v) {
    Bytes result(sizeof(v)); std::memcpy(result.data(), &v, sizeof(v)); return result;
}
template<class T> inline void put(Bytes& out, T v) { Bytes value = scalar(v); out.insert(out.end(), value.begin(), value.end()); }
inline void putBytes(Bytes& out, const Bytes& value) { put<uint32_t>(out, static_cast<uint32_t>(value.size())); out.insert(out.end(), value.begin(), value.end()); }
inline Bytes unicode(const std::string& value) { return bytes(rti::HLAunicodeString(wide(value)).encode()); }
inline std::string decodeUnicode(const Bytes& value) {
    rti::HLAunicodeString decoded; decoded.decode(blob(value)); return narrow(decoded.get());
}
struct Reader {
    const Bytes& source; size_t offset = 0;
    Bytes take(size_t count) {
        require(count <= source.size() - offset, "truncated spool");
        Bytes value(source.begin() + offset, source.begin() + offset + count); offset += count; return value;
    }
    template<class T> T read() { Bytes value = take(sizeof(T)); return little<T>(value.data()); }
    Bytes sized() { return take(read<uint32_t>()); }
    std::string text() {
        uint32_t count = read<uint32_t>(); require(count > 0 && count <= 1024, "invalid metadata string length");
        Bytes value = take(count);
        require(std::all_of(value.begin(), value.end(), [](unsigned char c) { return c >= 32 && c < 127; }), "prototype metadata requires printable ASCII UTF8 subset");
        return std::string(value.begin(), value.end());
    }
};
struct Body { std::string id, name; double radius, gm; };
struct Header { int32_t count; std::vector<Body> bodies; Bytes encoded; };
inline Header parseHeader(Reader& reader) {
    require(reader.take(8) == Bytes({'2','2','0','7','S','F','0','1'}), "spool magic mismatch");
    Header result; result.count = reader.read<int32_t>(); int32_t bodyCount = reader.read<int32_t>();
    require(result.count >= 8 && result.count <= 1000000 && bodyCount > 0 && bodyCount <= 64, "spool count outside bounded prototype limits");
    std::set<std::string> ids;
    for (int32_t i = 0; i < bodyCount; ++i) {
        Body body{reader.text(), reader.text(), reader.read<double>(), reader.read<double>()};
        require(ids.insert(body.id).second, "duplicate body id");
        require(std::isfinite(body.radius) && body.radius > 0 && std::isfinite(body.gm) && body.gm > 0, "invalid physical metadata");
        result.bodies.push_back(body);
    }
    result.encoded = Bytes(reader.source.begin(), reader.source.begin() + reader.offset); return result;
}
inline Bytes readFile(const std::string& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate); require(stream.good(), "cannot open spool");
    auto length = stream.tellg(); require(length > 0 && length <= 1024LL * 1024 * 1024, "invalid spool size");
    Bytes value(static_cast<size_t>(length)); stream.seekg(0); stream.read(reinterpret_cast<char*>(value.data()), length);
    require(stream.good(), "cannot read spool"); return value;
}
inline void validateState(const Bytes& state, double time) {
    require(state.size() == stateBytes, "state must contain 112 bytes");
    for (size_t i = 0; i < 14; ++i) require(std::isfinite(little<double>(state.data() + i * 8)), "nonfinite state");
    double norm = 0;
    for (size_t i = 6; i < 10; ++i) { double v = little<double>(state.data() + i * 8); norm += v * v; }
    require(std::abs(norm - 1.0) < 1e-9, "state quaternion not normalized");
    require(little<double>(state.data() + 104) == time, "state time disagrees with tick");
}
struct Class {
    rti::ObjectClassHandle handle; std::map<std::string,rti::AttributeHandle> attributes;
    rti::AttributeHandle at(const std::string& name) const { return attributes.at(name); }
    rti::AttributeHandleSet set() const { rti::AttributeHandleSet value; for (const auto& a : attributes) value.insert(a.second); return value; }
};
class Session : public rti::NullFederateAmbassador {
public:
    decltype(rti::RTIambassadorFactory().createRTIambassador()) ambassador;
    Class exco, reference, entity;
    rti::InteractionClassHandle mtr; rti::ParameterHandle mtrMode;
    std::set<std::wstring> announced, synced, reserved;
    std::map<rti::ObjectInstanceHandle,std::string> objectNames;
    bool constrained = false, regulating = false, granted = false;
    int64_t logicalUs = 0; std::string fault;
    std::wstring federation, federateName;
    // HLA save and restore. Each federate writes its own state as canonical bytes under the save label; a restored state must re-encode to the same bytes.
    std::filesystem::path stateDirectory{"."};
    std::wstring saveLabel, restoreLabel, restoreName;
    bool saveRequested = false, restoreRequested = false, saving = false, restoring = false;
    // restoreStarts counts restores from their first callback, since a federate loads its saved state before the federation reports it restored.
    int saveOutcome = 0, restoreAccepted = 0, restoreOutcome = 0, restores = 0, restoreStarts = 0;
    virtual Bytes saveState() const { return Bytes(); }
    virtual void restoreState(const Bytes&) {}
    Session() : ambassador(rti::RTIambassadorFactory().createRTIambassador()) {}
    void log(const std::string& event) { std::cout << event << " hlt_us=" << logicalUs << std::endl; }
    void pump() { ambassador->evokeMultipleCallbacks(0.001, 0.02); require(fault.empty(), fault); saveOrRestore(); if(!saving && !restoring) service(); }
    std::filesystem::path statePath(const std::wstring& label, const std::wstring& name) const { return stateDirectory / (narrow(label) + "." + narrow(name) + ".state"); }
    void saveOrRestore() {
        if (saveRequested) {
            saveRequested = false; ambassador->federateSaveBegun();
            Bytes state = saveState(); auto path = statePath(saveLabel, federateName);
            require(!std::filesystem::exists(path), "refusing to replace a saved state");
            std::ofstream stream(path, std::ios::binary); stream.write(reinterpret_cast<const char*>(state.data()), static_cast<std::streamsize>(state.size()));
            stream.close(); require(stream.good(), "cannot write saved state");
            ambassador->federateSaveComplete(); log("saved label=" + narrow(saveLabel) + " bytes=" + std::to_string(state.size()));
        }
        if (restoreRequested) {
            restoreRequested = false;
            std::ifstream stream(statePath(restoreLabel, restoreName), std::ios::binary); require(stream.good(), "saved state not found");
            stream.seekg(0, std::ios::end); auto length = stream.tellg(); require(length > 0 && length <= 1024LL * 1024 * 1024, "invalid saved state size");
            Bytes state(static_cast<size_t>(length)); stream.seekg(0); stream.read(reinterpret_cast<char*>(state.data()), length); require(stream.good(), "cannot read saved state");
            restoreState(state);
            require(saveState() == state, "restored state does not re-encode to the saved bytes");
            ambassador->federateRestoreComplete(); log("restored label=" + narrow(restoreLabel) + " bytes=" + std::to_string(state.size()) + " reencoded_identical");
        }
    }
    // Waits for the federation to finish restoring, then checks that the RTI's logical time matches the restored state.
    void afterRestore() {
        wait([&]{ return restoreOutcome != 0; }, "federation restored"); require(restoreOutcome == 1, "federation not restored"); restoreOutcome = 0;
        rti::HLAinteger64Time now; ambassador->queryLogicalTime(now); require(now.getTime() == logicalUs, "logical time differs from restored state");
        announced.clear(); synced.clear(); granted = false; log("federation_restored");
    }
    virtual void service() {}
    void wait(const std::function<bool()>& predicate, const std::string& label) {
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(30);
        while (!predicate()) { require(std::chrono::steady_clock::now() < deadline, "timeout: " + label); pump(); }
    }
    void connect(const std::string& url, const std::string& federationName) {
        federation = wide(federationName); ambassador->connect(*this,rti::HLA_EVOKED,wide(url)); log("connected");
    }
    Class lookup(const std::wstring& name, std::initializer_list<const char*> attributes) {
        Class result; result.handle = ambassador->getObjectClassHandle(name);
        for (const char* a : attributes) result.attributes.emplace(a,ambassador->getAttributeHandle(result.handle,wide(a)));
        return result;
    }
    void handles() {
        exco=lookup(L"HLAobjectRoot.ExecutionConfiguration",{"root_frame_name","scenario_time_epoch","current_execution_mode","next_execution_mode","next_mode_scenario_time","next_mode_cte_time","least_common_time_step"});
        reference=lookup(L"HLAobjectRoot.ReferenceFrame",{"name","parent_name","state"});
        entity=lookup(L"HLAobjectRoot.PhysicalEntity",{"name","type","status","parent_reference_frame","state","center_of_mass","body_wrt_structural"});
        mtr=ambassador->getInteractionClassHandle(L"HLAinteractionRoot.ModeTransitionRequest");
        mtrMode=ambassador->getParameterHandle(mtr,L"execution_mode");
    }
    rti::ObjectInstanceHandle add(const Class& cls, const std::string& name) {
        ambassador->reserveObjectInstanceName(wide(name)); wait([&]{return reserved.count(wide(name))!=0;},"reserve "+name);
        return ambassador->registerObjectInstance(cls.handle,wide(name));
    }
    void registerSync(const std::string& label) { announced.erase(wide(label)); synced.erase(wide(label)); ambassador->registerFederationSynchronizationPoint(wide(label),rti::VariableLengthData()); }
    // Registers a point for named federates only, so a federate that has joined is included even if its join is still settling.
    void registerSync(const std::string& label, const rti::FederateHandleSet& members) { announced.erase(wide(label)); synced.erase(wide(label)); ambassador->registerFederationSynchronizationPoint(wide(label),rti::VariableLengthData(),members); }
    void barrier(const std::string& label, bool master=false, const rti::FederateHandleSet* members=nullptr) {
        if(master) { if(members) registerSync(label,*members); else registerSync(label); }
        wait([&]{return announced.count(wide(label))!=0;},"announce "+label);
        ambassador->synchronizationPointAchieved(wide(label));
        wait([&]{return synced.count(wide(label))!=0;},"synchronize "+label);
        announced.erase(wide(label)); synced.erase(wide(label)); log("synchronized "+label);
    }
    void timeManagement() {
        ambassador->enableAsynchronousDelivery();
        ambassador->enableTimeConstrained(); wait([&]{return constrained;},"time constrained");
        ambassador->enableTimeRegulation(rti::HLAinteger64Interval(stepUs)); wait([&]{return regulating;},"time regulating");
        log("time_constrained_and_regulating lookahead_us=15625");
    }
    void advance(int64_t target) {
        require(target > logicalUs,"nonmonotonic logical advance"); granted=false;
        ambassador->timeAdvanceRequest(rti::HLAinteger64Time(target)); wait([&]{return granted;},"time advance");
        require(logicalUs==target,"unexpected time grant");
    }
    void finish() { ambassador->resignFederationExecution(rti::CANCEL_THEN_DELETE_THEN_DIVEST); ambassador->disconnect(); log("resigned_disconnected"); }
    void announceSynchronizationPoint(const std::wstring& label,const rti::VariableLengthData&) override { announced.insert(label); }
    void federationSynchronized(const std::wstring& label,const rti::FederateHandleSet& failed) override { if(!failed.empty()) fault="failed synchronization"; synced.insert(label); }
    void synchronizationPointRegistrationFailed(const std::wstring& label,rti::SynchronizationPointFailureReason) override { fault="sync registration failed: "+narrow(label); }
    void objectInstanceNameReservationSucceeded(const std::wstring& name) override { reserved.insert(name); }
    void objectInstanceNameReservationFailed(const std::wstring& name) override { fault="name reservation failed: "+narrow(name); }
    void discoverObjectInstance(rti::ObjectInstanceHandle object,rti::ObjectClassHandle,const std::wstring& name) override { objectNames.emplace(object,narrow(name)); log("discovered "+narrow(name)); }
    void discoverObjectInstance(rti::ObjectInstanceHandle object,rti::ObjectClassHandle cls,const std::wstring& name,rti::FederateHandle) override { discoverObjectInstance(object,cls,name); }
    void timeConstrainedEnabled(const rti::LogicalTime&) override { constrained=true; }
    void timeRegulationEnabled(const rti::LogicalTime& t) override { regulating=true; logicalUs=rti::HLAinteger64Time(t).getTime(); }
    void timeAdvanceGrant(const rti::LogicalTime& t) override { granted=true; logicalUs=rti::HLAinteger64Time(t).getTime(); }
    void connectionLost(const std::wstring& why) override { fault="connection lost: "+narrow(why); }
    void initiateFederateSave(const std::wstring& label) override { saveLabel=label; saveRequested=true; saving=true; }
    void initiateFederateSave(const std::wstring& label,const rti::LogicalTime&) override { initiateFederateSave(label); }
    void federationSaved() override { saving=false; saveOutcome=1; }
    void federationNotSaved(rti::SaveFailureReason) override { saving=false; saveOutcome=-1; }
    void requestFederationRestoreSucceeded(const std::wstring&) override { restoreAccepted=1; }
    void requestFederationRestoreFailed(const std::wstring&) override { restoreAccepted=-1; }
    void federationRestoreBegun() override { if(!restoring) ++restoreStarts; restoring=true; }
    void initiateFederateRestore(const std::wstring& label,const std::wstring& name,rti::FederateHandle) override { if(!restoring) ++restoreStarts; restoring=true; restoreLabel=label; restoreName=name; restoreRequested=true; }
    void federationRestored() override { restoring=false; restoreOutcome=1; ++restores; }
    void federationNotRestored(rti::RestoreFailureReason) override { restoring=false; restoreOutcome=-1; }
};
inline rti::AttributeHandleValueMap values(const Class& cls, std::initializer_list<std::pair<std::string,Bytes>> attributes) {
    rti::AttributeHandleValueMap result; for(const auto& a:attributes) result.emplace(cls.at(a.first),blob(a.second)); return result;
}
}
