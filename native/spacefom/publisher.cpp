#include "transport.hpp"
using namespace sf;

class Publisher final : public Session {
public:
    std::vector<int16_t> requests;
    std::map<rti::ObjectInstanceHandle,rti::AttributeHandleValueMap> latest;
    std::set<rti::ObjectInstanceHandle> pending;
    void provideAttributeValueUpdate(rti::ObjectInstanceHandle object,const rti::AttributeHandleSet&,const rti::VariableLengthData&) override { pending.insert(object); }
    // Answers update requests, such as a SpaceFOM late joiner's ExCO request, outside the callback with the latest untagged values.
    void service() override {
        std::set<rti::ObjectInstanceHandle> requested; requested.swap(pending);
        for(const auto& object:requested) {
            auto found=latest.find(object);
            if(found!=latest.end()) {ambassador->updateAttributeValues(object,found->second,rti::VariableLengthData());log("provided_update");}
        }
    }
    void receiveInteraction(rti::InteractionClassHandle cls,const rti::ParameterHandleValueMap& params,const rti::VariableLengthData&,rti::OrderType,rti::TransportationType,rti::SupplementalReceiveInfo) override {
        try {
            require(cls==mtr,"unexpected interaction"); Bytes value=bytes(params.at(mtrMode));
            require(value.size()==2,"invalid MTR width"); int16_t mode=little<int16_t>(value.data());
            require(mode>=2 && mode<=4,"invalid MTR mode"); requests.push_back(mode); log("received_mtr mode="+std::to_string(mode));
        } catch(const std::exception& e) { fault=e.what(); }
    }
    // Saved state: the current tick, logical time, the ExCO modes last sent and any mode requests not yet consumed.
    int32_t currentTick=0; int16_t excoCurrent=1,excoNext=1; double excoTime=0;
    Bytes saveState() const override {
        Bytes out{'2','2','0','7','F','S','P','1'};
        put(out,currentTick);put(out,logicalUs);put(out,excoCurrent);put(out,excoNext);put(out,excoTime);
        put<uint32_t>(out,static_cast<uint32_t>(requests.size()));for(int16_t mode:requests)put(out,mode);
        return out;
    }
    void restoreState(const Bytes& state) override {
        Reader reader{state};require(reader.take(8)==Bytes({'2','2','0','7','F','S','P','1'}),"publisher state magic mismatch");
        currentTick=reader.read<int32_t>();logicalUs=reader.read<int64_t>();excoCurrent=reader.read<int16_t>();excoNext=reader.read<int16_t>();excoTime=reader.read<double>();
        uint32_t count=reader.read<uint32_t>();require(count<=16,"too many saved mode requests");
        requests.clear();for(uint32_t k=0;k<count;++k)requests.push_back(reader.read<int16_t>());
        require(reader.offset==state.size(),"publisher state trailing bytes");pending.clear();
    }
    void expectRequest(int16_t mode) {
        wait([&]{return !requests.empty();},"MTR "+std::to_string(mode));
        require(requests.front()==mode,"unexpected MTR transition"); requests.erase(requests.begin());
    }
};

int main(int argc,char** argv) {
    try {
        require(argc>=5,"usage: spacefom-publisher input.spool fom-directory rti://127.0.0.1:port federation [--master-modes] [--required <federate>] [--save-restore] [--state-dir <directory>]");
        // --master-modes: the Master schedules freeze, resume and shutdown itself instead of waiting for requests.
        // --save-restore: with --master-modes, save the federation at the midpoint freeze, freeze again at three quarters and restore the midpoint save.
        bool masterModes=false,saveRestore=false; std::wstring required=L"orbital_observer"; std::filesystem::path stateDirectory{"."};
        for(int a=5;a<argc;++a) {
            std::string option=argv[a];
            if(option=="--master-modes") masterModes=true;
            else if(option=="--required" && a+1<argc) required=wide(argv[++a]);
            else if(option=="--save-restore") saveRestore=true;
            else if(option=="--state-dir" && a+1<argc) stateDirectory=argv[++a];
            else throw std::runtime_error("unknown option: "+option);
        }
        require(!saveRestore || masterModes,"--save-restore requires --master-modes");
        Bytes source=readFile(argv[1]); Reader reader{source}; Header header=parseHeader(reader);
        const size_t recordSize=40+(header.bodies.size()+1)*stateBytes;
        require(source.size()==reader.offset+static_cast<size_t>(header.count)*recordSize,"spool file length mismatch");
        size_t frameOffset=reader.offset;
        const double epoch=little<double>(source.data()+frameOffset+40+104);
        require(epoch>7000000000.0 && epoch<8000000000.0,"prototype requires 2207 TT seconds from TJD origin");
        for(int32_t i=0;i<header.count;++i) {
            const size_t offset=frameOffset+static_cast<size_t>(i)*recordSize;
            require(little<int64_t>(source.data()+offset)==i,"ticks must be contiguous from zero");
            for(size_t j=0;j<=header.bodies.size();++j) {
                const size_t start=offset+40+j*stateBytes;
                validateState(Bytes(source.begin()+start,source.begin()+start+stateBytes),epoch+static_cast<double>(i)/64.0);
            }
        }
        Publisher session; session.stateDirectory=stateDirectory; session.federateName=L"orbital_master"; session.connect(argv[3],argv[4]);
        std::vector<std::wstring> modules;
        for(const char* module:{"datatypes","management","environment","entity","switches"})
            modules.push_back((std::filesystem::path(argv[2])/(std::string("SISO_SpaceFOM_")+module+".xml")).wstring());
        session.ambassador->createFederationExecution(session.federation,modules,L"HLAinteger64Time");
        rti::FederateHandle self=session.ambassador->joinFederationExecution(session.federateName,L"orbital_spacefom_publisher",session.federation);
        session.handles();
        session.ambassador->publishObjectClassAttributes(session.exco.handle,session.exco.set());
        session.ambassador->publishObjectClassAttributes(session.reference.handle,session.reference.set());
        session.ambassador->publishObjectClassAttributes(session.entity.handle,session.entity.set());
        session.ambassador->subscribeInteractionClass(session.mtr);
        auto exco=session.add(session.exco,"ExCO");
        auto root=session.add(session.reference,rootName);
        auto vessel=session.add(session.entity,"orbital_vessel");
        std::vector<rti::ObjectInstanceHandle> bodies;
        for(const Body& body:header.bodies) bodies.push_back(session.add(session.reference,"body_"+body.id));
        rti::FederateHandle peer;
        session.wait([&]{try {peer=session.ambassador->getFederateHandle(required);return true;}catch(const rti::NameNotFound&){return false;}},"required observer join");
        // Early-joiner initialization points name the required federate explicitly, so it is always in the synchronization set.
        rti::FederateHandleSet early{self,peer};
        session.registerSync("initialization_started",early);
        session.registerSync("root_frame_discovered",early);
        session.registerSync("prototype_metadata",early);
        session.barrier("objects_discovered",true,&early);
        auto excoAttributes=[&](int16_t current,int16_t next,double nextTime) {
            return values(session.exco,{{"root_frame_name",unicode(rootName)},{"scenario_time_epoch",scalar(epoch)},
                {"current_execution_mode",scalar(current)},{"next_execution_mode",scalar(next)},
                {"next_mode_scenario_time",scalar(nextTime)},{"next_mode_cte_time",scalar(-std::numeric_limits<double>::max())},
                {"least_common_time_step",bytes(rti::HLAinteger64Time(stepUs).encode())}});
        };
        auto excoUpdate=[&](int16_t current,int16_t next,double nextTime,const Bytes& tag=Bytes()) {
            auto attrs=excoAttributes(current,next,nextTime);
            session.ambassador->updateAttributeValues(exco,attrs,blob(tag));session.latest[exco]=attrs;
            session.excoCurrent=current;session.excoNext=next;session.excoTime=nextTime;
            session.log("exco current="+std::to_string(current)+" next="+std::to_string(next));
        };
        excoUpdate(1,1,epoch,header.encoded);
        Bytes rootState(stateBytes,0); double one=1; std::memcpy(rootState.data()+48,&one,8);std::memcpy(rootState.data()+104,&epoch,8);
        session.latest[root]=values(session.reference,{{"name",unicode(rootName)},{"parent_name",unicode("")},{"state",rootState}});
        session.ambassador->updateAttributeValues(root,session.latest[root],rti::VariableLengthData());
        // A SpaceFOM Master updates the ExCO again once the root frame is published; peers wait for it before root_frame_discovered (SISO-STD-018-2020 figure 7-6).
        excoUpdate(1,1,epoch);
        session.barrier("root_frame_discovered");
        Bytes zeroVector(24,0),identity(32,0);std::memcpy(identity.data(),&one,8);
        session.latest[vessel]=values(session.entity,{{"name",unicode("orbital_vessel")},{"type",unicode("OrbitalFlightPrototype")},{"status",unicode("coast")},{"parent_reference_frame",unicode(rootName)},{"center_of_mass",zeroVector},{"body_wrt_structural",identity}});
        session.ambassador->updateAttributeValues(vessel,session.latest[vessel],rti::VariableLengthData());
        for(size_t j=0;j<bodies.size();++j) {
            session.latest[bodies[j]]=values(session.reference,{{"name",unicode("body_"+header.bodies[j].id)},{"parent_name",unicode(rootName)}});
            session.ambassador->updateAttributeValues(bodies[j],session.latest[bodies[j]],rti::VariableLengthData());
        }
        auto publishFrame=[&](int32_t index,bool timed) {
            size_t offset=frameOffset+static_cast<size_t>(index)*recordSize;
            Bytes tag(source.begin()+offset,source.begin()+offset+40);
            for(size_t j=0;j<=bodies.size();++j) {
                size_t begin=offset+40+j*stateBytes; Bytes state(source.begin()+begin,source.begin()+begin+stateBytes);
                const Class& cls=j==0?session.entity:session.reference;
                auto object=j==0?vessel:bodies[j-1];
                auto attrs=j==0
                    ? values(cls,{{"name",unicode("orbital_vessel")},{"type",unicode("OrbitalFlightPrototype")},{"status",unicode("coast")},{"parent_reference_frame",unicode(rootName)},{"center_of_mass",zeroVector},{"body_wrt_structural",identity},{"state",state}})
                    : values(cls,{{"name",unicode("body_"+header.bodies[j-1].id)},{"parent_name",unicode(rootName)},{"state",state}});
                if(timed) session.ambassador->updateAttributeValues(object,attrs,blob(tag),rti::HLAinteger64Time(static_cast<int64_t>(index)*stepUs));
                else session.ambassador->updateAttributeValues(object,attrs,blob(tag));
            }
        };
        publishFrame(0,false);
        session.barrier("prototype_metadata");
        // Multiphase initialization data is sent again after prototype_metadata, where a SpaceFOM peer waits for it to change.
        session.ambassador->updateAttributeValues(root,session.latest[root],rti::VariableLengthData());
        session.ambassador->updateAttributeValues(vessel,session.latest[vessel],rti::VariableLengthData());
        for(const auto& body:bodies) session.ambassador->updateAttributeValues(body,session.latest[body],rti::VariableLengthData());
        session.barrier("initialization_started");
        session.registerSync("initialization_completed");
        session.timeManagement();
        excoUpdate(1,2,epoch);session.barrier("mtr_run",true);excoUpdate(2,2,epoch);session.log("run");
        const int32_t freeze=header.count/2,rewind=saveRestore?freeze+header.count/4:-1;
        const std::wstring saveLabel=L"freeze_"+std::to_wstring(freeze);
        bool restored=false;
        // Master-scheduled freezes are announced one second ahead so every federate can schedule the target.
        auto lead=[](int32_t target){return target-std::min<int32_t>(64,target-1);};
        for(int32_t i=1;i<header.count;++i) {
            if(masterModes && i==lead(freeze)) excoUpdate(2,3,epoch+static_cast<double>(freeze)/64.0);
            if(saveRestore && !restored && i==lead(rewind)) excoUpdate(2,3,epoch+static_cast<double>(rewind)/64.0);
            if(i==freeze && !masterModes) {session.expectRequest(3);excoUpdate(2,3,epoch+static_cast<double>(i)/64.0);}
            publishFrame(i,true); session.advance(static_cast<int64_t>(i)*stepUs); session.currentTick=i;
            if(i==freeze || (saveRestore && !restored && i==rewind)) {
                session.barrier("mtr_freeze",true);excoUpdate(3,3,epoch+static_cast<double>(i)/64.0);session.log("freeze");
                if(saveRestore && i==freeze) {
                    session.saveOutcome=0;session.ambassador->requestFederationSave(saveLabel);
                    session.wait([&]{return session.saveOutcome!=0;},"federation saved");require(session.saveOutcome==1,"federation not saved");session.log("federation_saved");
                }
                if(i==rewind) {
                    // Restores the midpoint save; every federate returns to that freeze and the run continues from there.
                    session.restoreAccepted=0;session.ambassador->requestFederationRestore(saveLabel);
                    session.wait([&]{return session.restoreAccepted!=0;},"restore request");require(session.restoreAccepted==1,"restore request refused");
                    session.afterRestore();restored=true;i=session.currentTick;session.latest[exco]=excoAttributes(session.excoCurrent,session.excoNext,session.excoTime);
                    session.log("rewound tick="+std::to_string(i));
                }
                if(masterModes) {auto end=std::chrono::steady_clock::now()+std::chrono::milliseconds(250);while(std::chrono::steady_clock::now()<end)session.pump();}
                else session.expectRequest(2);
                excoUpdate(3,2,epoch+static_cast<double>(i)/64.0);session.barrier("mtr_run",true);excoUpdate(2,2,epoch+static_cast<double>(i)/64.0);session.log("run");
            }
        }
        if(!masterModes)session.expectRequest(4);
        excoUpdate(2,4,epoch+static_cast<double>(header.count-1)/64.0);
        session.registerSync("mtr_shutdown");session.log("shutdown_marker_registered_unachieved");session.log("shutdown frames="+std::to_string(header.count));
        session.ambassador->resignFederationExecution(rti::CANCEL_THEN_DELETE_THEN_DIVEST);
        session.wait([&]{try {session.ambassador->destroyFederationExecution(session.federation);return true;}catch(const rti::FederatesCurrentlyJoined&){return false;}},"destroy federation");
        session.ambassador->disconnect();session.log("destroyed_disconnected");return 0;
    } catch(const rti::Exception& e) {std::wcerr<<L"RTI failure: "<<e.what()<<std::endl;}
      catch(const std::exception& e) {std::cerr<<"failure: "<<e.what()<<std::endl;}
    return 1;
}
