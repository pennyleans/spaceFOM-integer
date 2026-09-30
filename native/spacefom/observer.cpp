#include "transport.hpp"
using namespace sf;

struct ReceivedFrame { Bytes tag; std::map<std::string,Bytes> states; };
class Observer final : public Session {
public:
    Header header{}; bool metadata=false,rootSeen=false,entitySeen=false;
    std::set<std::string> bodyStatic;
    double epoch=0;int16_t current=0,next=0;double transitionTime=0;
    std::map<int64_t,ReceivedFrame> frames,firstPass;
    size_t timestampedUpdates=0,receiveOrderUpdates=0;
    int32_t currentTick=0;
    // Saved state: tick, logical time, ExCO view, counters, static discoveries and every frame received so far, in key order.
    Bytes saveState() const override {
        Bytes out{'2','2','0','7','F','S','O','1'};
        put(out,currentTick);put(out,logicalUs);put(out,current);put(out,next);put(out,transitionTime);put(out,epoch);
        put<uint64_t>(out,timestampedUpdates);put<uint64_t>(out,receiveOrderUpdates);
        put<uint8_t>(out,metadata?1:0);put<uint8_t>(out,rootSeen?1:0);put<uint8_t>(out,entitySeen?1:0);putBytes(out,header.encoded);
        put<uint32_t>(out,static_cast<uint32_t>(bodyStatic.size()));for(const std::string& name:bodyStatic)putBytes(out,Bytes(name.begin(),name.end()));
        put<uint32_t>(out,static_cast<uint32_t>(frames.size()));
        for(const auto& frame:frames) {
            put(out,frame.first);putBytes(out,frame.second.tag);put<uint32_t>(out,static_cast<uint32_t>(frame.second.states.size()));
            for(const auto& state:frame.second.states){putBytes(out,Bytes(state.first.begin(),state.first.end()));putBytes(out,state.second);}
        }
        return out;
    }
    void restoreState(const Bytes& state) override {
        Reader reader{state};require(reader.take(8)==Bytes({'2','2','0','7','F','S','O','1'}),"observer state magic mismatch");
        int32_t savedTick=reader.read<int32_t>();
        // Frames received after the save are kept aside so the run after the restore can be compared with them.
        for(const auto& frame:frames) if(frame.first>savedTick) firstPass.insert(frame);
        currentTick=savedTick;logicalUs=reader.read<int64_t>();current=reader.read<int16_t>();next=reader.read<int16_t>();transitionTime=reader.read<double>();epoch=reader.read<double>();
        timestampedUpdates=static_cast<size_t>(reader.read<uint64_t>());receiveOrderUpdates=static_cast<size_t>(reader.read<uint64_t>());
        metadata=reader.take(1)[0]!=0;rootSeen=reader.take(1)[0]!=0;entitySeen=reader.take(1)[0]!=0;
        require(reader.sized()==header.encoded,"restored metadata differs");
        bodyStatic.clear();for(uint32_t k=reader.read<uint32_t>();k>0;--k){Bytes name=reader.sized();bodyStatic.insert(std::string(name.begin(),name.end()));}
        frames.clear();
        for(uint32_t k=reader.read<uint32_t>();k>0;--k) {
            int64_t key=reader.read<int64_t>();ReceivedFrame& frame=frames[key];frame.tag=reader.sized();
            for(uint32_t m=reader.read<uint32_t>();m>0;--m){Bytes name=reader.sized();frame.states.emplace(std::string(name.begin(),name.end()),reader.sized());}
        }
        require(reader.offset==state.size(),"observer state trailing bytes");
    }
    void reflect(rti::ObjectInstanceHandle object,const rti::AttributeHandleValueMap& attrs,const rti::VariableLengthData& tag,const rti::LogicalTime* time,rti::OrderType received) {
        try {
            const std::string& name=objectNames.at(object);
            auto obtain=[&](const Class& cls,const std::string& a) {return bytes(attrs.at(cls.at(a)));};
            if(name=="ExCO") {
                require(!time,"ExCO must use receive order");
                require(decodeUnicode(obtain(exco,"root_frame_name"))==rootName,"wrong root frame");
                Bytes encodedEpoch=obtain(exco,"scenario_time_epoch");require(encodedEpoch.size()==8,"epoch size");
                double receivedEpoch=little<double>(encodedEpoch.data());
                require(std::isfinite(receivedEpoch) && receivedEpoch>7e9 && receivedEpoch<8e9,"invalid scenario epoch");
                if(metadata) {require(epoch==receivedEpoch,"epoch changed");} epoch=receivedEpoch;
                Bytes c=obtain(exco,"current_execution_mode"),n=obtain(exco,"next_execution_mode"),t=obtain(exco,"next_mode_scenario_time");
                require(c.size()==2 && n.size()==2 && t.size()==8,"ExCO field width");
                current=little<int16_t>(c.data());next=little<int16_t>(n.data());transitionTime=little<double>(t.data());
                require(current>=0 && current<=4 && next>=0 && next<=4,"ExCO mode range");
                rti::HLAinteger64Time lcts;lcts.decode(blob(obtain(exco,"least_common_time_step")));require(lcts.getTime()==stepUs,"wrong LCTS");
                if(tag.size()!=0) {
                    require(!metadata,"duplicate metadata");Bytes metadataBytes=bytes(tag);Reader reader{metadataBytes};header=parseHeader(reader);
                    require(reader.offset==metadataBytes.size(),"metadata trailing bytes");metadata=true;
                }
                log("exco current="+std::to_string(current)+" next="+std::to_string(next));return;
            }
            if(name==rootName) {
                require(decodeUnicode(obtain(reference,"name"))==rootName,"root name mismatch");
                require(decodeUnicode(obtain(reference,"parent_name")).empty(),"root must have no parent");
                validateState(obtain(reference,"state"),epoch);rootSeen=true;return;
            }
            bool vessel=name=="orbital_vessel"; const Class& cls=vessel?entity:reference;
            auto state=attrs.find(cls.at("state"));
            if(attrs.count(cls.at("name"))) {
                require(decodeUnicode(obtain(cls,"name"))==name,"static name mismatch");
                require(decodeUnicode(obtain(cls,vessel?"parent_reference_frame":"parent_name"))==rootName,"parent frame mismatch");
                if(vessel) {
                    require(decodeUnicode(obtain(entity,"type"))=="OrbitalFlightPrototype","entity type mismatch");
                    require(decodeUnicode(obtain(entity,"status"))=="coast","entity status mismatch");
                    require(obtain(entity,"center_of_mass")==Bytes(24,0),"unexpected center of mass");
                    Bytes identity(32,0);double one=1;std::memcpy(identity.data(),&one,8);
                    require(obtain(entity,"body_wrt_structural")==identity,"unexpected body frame");entitySeen=true;
                } else bodyStatic.insert(name);
            }
            if(state==attrs.end())return;
            require(metadata,"state received before metadata");
            Bytes provenance=bytes(tag);require(provenance.size()==40,"provenance tag width");
            int64_t tick=little<int64_t>(provenance.data());require(tick>=0 && tick<header.count,"tick range");
            if(tick==0) {require(!time,"initial frame must be receive order");++receiveOrderUpdates;}
            else {require(time && received==rti::TIMESTAMP,"state must be timestamp ordered");require(rti::HLAinteger64Time(*time).getTime()==tick*stepUs,"HLA timestamp mismatch");++timestampedUpdates;}
            Bytes encoded=bytes(state->second);validateState(encoded,epoch+static_cast<double>(tick)/64.0);
            ReceivedFrame& frame=frames[tick];if(frame.tag.empty())frame.tag=provenance;else require(frame.tag==provenance,"provenance differs among objects");
            require(frame.states.emplace(name,encoded).second,"duplicate state update");
        }catch(const std::exception& e){fault=e.what();}catch(const rti::Exception& e){fault=narrow(e.what());}
    }
    void reflectAttributeValues(rti::ObjectInstanceHandle object,const rti::AttributeHandleValueMap& attrs,const rti::VariableLengthData& tag,rti::OrderType,rti::TransportationType,rti::SupplementalReflectInfo) override {reflect(object,attrs,tag,nullptr,rti::RECEIVE);}
    void reflectAttributeValues(rti::ObjectInstanceHandle object,const rti::AttributeHandleValueMap& attrs,const rti::VariableLengthData& tag,rti::OrderType,rti::TransportationType,const rti::LogicalTime& time,rti::OrderType order,rti::SupplementalReflectInfo) override {reflect(object,attrs,tag,&time,order);}
    void reflectAttributeValues(rti::ObjectInstanceHandle object,const rti::AttributeHandleValueMap& attrs,const rti::VariableLengthData& tag,rti::OrderType,rti::TransportationType,const rti::LogicalTime& time,rti::OrderType order,rti::MessageRetractionHandle,rti::SupplementalReflectInfo) override {reflect(object,attrs,tag,&time,order);}
    bool complete(int64_t tick) const {auto frame=frames.find(tick);return frame!=frames.end() && frame->second.states.size()==header.bodies.size()+1;}
    // After a grant without a complete frame, records which objects are missing and whether they arrive late, then fails.
    void failIncomplete(int64_t tick) {
        auto missing=[&]{std::string names;auto frame=frames.find(tick);
            for(const std::string& name:expectedObjects()) if(frame==frames.end() || !frame->second.states.count(name)) names+=(names.empty()?"":",")+name;
            return names;};
        log("incomplete_at_grant tick="+std::to_string(tick)+" missing="+missing());
        auto start=std::chrono::steady_clock::now(),end=start+std::chrono::milliseconds(1000);
        while(!complete(tick) && std::chrono::steady_clock::now()<end) {ambassador->evokeMultipleCallbacks(0.001,0.02);}
        auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
        log(complete(tick) ? "late_completion tick="+std::to_string(tick)+" after_grant_ms="+std::to_string(ms)
                           : "still_missing tick="+std::to_string(tick)+" after_ms=1000 missing="+missing());
        throw std::runtime_error("time grant without complete frame");
    }
    std::vector<std::string> expectedObjects() const {std::vector<std::string> names{"orbital_vessel"};for(const Body& body:header.bodies)names.push_back("body_"+body.id);return names;}
    void request(int16_t mode) {wait([&]{return !saving && !restoring;},"save or restore to finish");rti::ParameterHandleValueMap parameters;parameters.emplace(mtrMode,blob(scalar(mode)));ambassador->sendInteraction(mtr,parameters,rti::VariableLengthData());log("sent_mtr mode="+std::to_string(mode));}
    void expectMode(int16_t mode) {wait([&]{return next==mode;},"ExCO next mode "+std::to_string(mode));}
    // Holds a freeze until the Master resumes. A federation restore during the freeze returns the tick of the restored save.
    int32_t frozen(int32_t at) {
        barrier("mtr_freeze");log("freeze");int64_t frozenUs=logicalUs;size_t frozenUpdates=timestampedUpdates;const int before=restoreStarts;
        auto end=std::chrono::steady_clock::now()+std::chrono::milliseconds(100);
        while(std::chrono::steady_clock::now()<end)pump();
        if(restoreStarts==before){require(logicalUs==frozenUs && timestampedUpdates==frozenUpdates,"logical time or state changed during freeze");log("freeze_verified wall_ms=100 no_time_advance");}
        request(2);wait([&]{return next==2 || restoreStarts!=before;},"ExCO next mode 2 or restore");
        if(restoreStarts!=before){afterRestore();at=currentTick;log("rewound tick="+std::to_string(at));expectMode(2);}
        barrier("mtr_run");log("run");return at;
    }
    void write(const std::string& path) {
        require(frames.size()==static_cast<size_t>(header.count),"missing frame");
        require(timestampedUpdates==static_cast<size_t>(header.count-1)*(header.bodies.size()+1),"TSO update count");
        require(receiveOrderUpdates==header.bodies.size()+1,"initial update count");
        // Frames received before a restore must equal the same frames received again after it.
        for(const auto& frame:firstPass) {const ReceivedFrame& again=frames.at(frame.first);require(frame.second.tag==again.tag && frame.second.states==again.states,"frame differs after restore: tick "+std::to_string(frame.first));}
        if(!firstPass.empty())log("rematerialized_identical frames="+std::to_string(firstPass.size())+" from="+std::to_string(firstPass.begin()->first)+" to="+std::to_string(firstPass.rbegin()->first));
        std::filesystem::path output(path),partial(path+".partial");require(!std::filesystem::exists(output)&&!std::filesystem::exists(partial),"refusing to replace existing observer output");
        std::ofstream stream(partial,std::ios::binary);require(stream.good(),"cannot create observer output");
        auto append=[&](const Bytes& value){stream.write(reinterpret_cast<const char*>(value.data()),static_cast<std::streamsize>(value.size()));};
        append(header.encoded);
        for(int64_t tick=0;tick<header.count;++tick) {
            require(complete(tick),"incomplete frame");ReceivedFrame& frame=frames.at(tick);append(frame.tag);append(frame.states.at("orbital_vessel"));
            for(const Body& body:header.bodies)append(frame.states.at("body_"+body.id));
        }
        stream.flush();require(stream.good(),"observer output write failed");stream.close();std::filesystem::rename(partial,output);
        log("observed_spool_committed frames="+std::to_string(header.count)+" tso_updates="+std::to_string(timestampedUpdates)+" provenance_is_not_authority");
    }
};
int main(int argc,char** argv) {
    try {
        require(argc==4 || (argc==6 && std::string(argv[4])=="--state-dir"),"usage: spacefom-observer output.spool rti://127.0.0.1:port federation [--state-dir <directory>]");
        require(!std::filesystem::exists(argv[1]),"refusing existing output");
        Observer session;if(argc==6)session.stateDirectory=argv[5];session.federateName=L"orbital_observer";session.connect(argv[2],argv[3]);
        session.wait([&]{try {session.ambassador->joinFederationExecution(session.federateName,L"independent_spacefom_observer",session.federation);return true;}catch(const rti::FederationExecutionDoesNotExist&){std::this_thread::sleep_for(std::chrono::milliseconds(20));return false;}},"federation creation");
        session.handles();session.ambassador->subscribeObjectClassAttributes(session.exco.handle,session.exco.set());
        session.ambassador->subscribeObjectClassAttributes(session.reference.handle,session.reference.set());session.ambassador->subscribeObjectClassAttributes(session.entity.handle,session.entity.set());
        session.ambassador->publishInteractionClass(session.mtr);
        session.wait([&]{std::set<std::string> names;for(const auto& o:session.objectNames)names.insert(o.second);return names.count("ExCO")&&names.count(rootName)&&names.count("orbital_vessel");},"required objects");
        session.barrier("objects_discovered");
        session.wait([&]{return session.metadata&&session.rootSeen;},"epoch and root");session.barrier("root_frame_discovered");
        session.wait([&]{return session.entitySeen&&session.bodyStatic.size()==session.header.bodies.size()&&session.complete(0);},"static attributes and initial state");
        session.barrier("prototype_metadata");session.barrier("initialization_started");
        session.wait([&]{return session.announced.count(L"initialization_completed")!=0;},"initialization complete marker");
        session.timeManagement();session.expectMode(2);session.barrier("mtr_run");session.log("run");
        const int32_t freeze=session.header.count/2;
        for(int32_t i=1;i<session.header.count;++i) {
            if(i==freeze && session.restores==0){session.expectMode(3);require(session.transitionTime==session.epoch+static_cast<double>(i)/64.0,"freeze target mismatch");}
            session.advance(static_cast<int64_t>(i)*stepUs);session.currentTick=i;
            if(!session.complete(i)) session.failIncomplete(i);
            if(i==freeze-1 && session.restores==0)session.request(3);
            // Any freeze the Master has announced for this tick, including one it scheduled without a request.
            if(session.next==3 && session.current!=3 && session.transitionTime==session.epoch+static_cast<double>(i)/64.0) i=session.frozen(i);
        }
        session.request(4);session.expectMode(4);session.log("shutdown_immediate_marker_not_achieved");session.finish();session.write(argv[1]);return 0;
    }catch(const rti::Exception& e){std::wcerr<<L"RTI failure: "<<e.what()<<std::endl;}
    catch(const std::exception& e){std::cerr<<"failure: "<<e.what()<<std::endl;}
    return 1;
}
