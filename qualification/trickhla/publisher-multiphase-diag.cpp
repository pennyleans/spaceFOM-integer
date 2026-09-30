// Diagnostic copy of native/spacefom/publisher.cpp at 131962d with two additions,
// used for the round 4 TrickHLA run and kept here so the finding is reproducible.
//
// Addition 1, after the root frame publication: a second ExCO update. A SpaceFOM
// Master sends the ExCO again after the root reference frame is published, and a
// federate that follows SISO-STD-018-2020 figure 7-6 waits for that update before
// it achieves root_frame_discovered. Without it the peer blocks in
// ExecutionConfiguration::wait_for_update() while the publisher waits at the
// root_frame_discovered synchronization point.
//
// Addition 2, after the prototype_metadata synchronization point: a repeat of the
// initial data (root frame, vessel and bodies). TrickHLA's multiphase
// initialization waits in Manager::receive_init_data for each required object's
// initial data to change, and the root frame is otherwise sent only once, before
// the multiphase window opens.
//
// This file is not part of the adapter build. It was compiled once in a scratch
// directory and used only for the diagnostic runs recorded in
// evidence/interop/round4/observer-variant and observer-variant2.

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
    void expectRequest(int16_t mode) {
        wait([&]{return !requests.empty();},"MTR "+std::to_string(mode));
        require(requests.front()==mode,"unexpected MTR transition"); requests.erase(requests.begin());
    }
};

int main(int argc,char** argv) {
    try {
        require(argc>=5,"usage: spacefom-publisher input.spool fom-directory rti://127.0.0.1:port federation [--master-modes] [--required <federate>]");
        // --master-modes: the Master schedules freeze, resume and shutdown itself instead of waiting for requests.
        bool masterModes=false; std::wstring required=L"orbital_observer";
        for(int a=5;a<argc;++a) {
            std::string option=argv[a];
            if(option=="--master-modes") masterModes=true;
            else if(option=="--required" && a+1<argc) required=wide(argv[++a]);
            else throw std::runtime_error("unknown option: "+option);
        }
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
        Publisher session; session.connect(argv[3],argv[4]);
        std::vector<std::wstring> modules;
        for(const char* module:{"datatypes","management","environment","entity","switches"})
            modules.push_back((std::filesystem::path(argv[2])/(std::string("SISO_SpaceFOM_")+module+".xml")).wstring());
        session.ambassador->createFederationExecution(session.federation,modules,L"HLAinteger64Time");
        rti::FederateHandle self=session.ambassador->joinFederationExecution(L"orbital_master",L"orbital_spacefom_publisher",session.federation);
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
        auto excoUpdate=[&](int16_t current,int16_t next,double nextTime,const Bytes& tag=Bytes()) {
            auto attrs=values(session.exco,{{"root_frame_name",unicode(rootName)},{"scenario_time_epoch",scalar(epoch)},
                {"current_execution_mode",scalar(current)},{"next_execution_mode",scalar(next)},
                {"next_mode_scenario_time",scalar(nextTime)},{"next_mode_cte_time",scalar(-std::numeric_limits<double>::max())},
                {"least_common_time_step",bytes(rti::HLAinteger64Time(stepUs).encode())}});
            session.ambassador->updateAttributeValues(exco,attrs,blob(tag));session.latest[exco]=attrs;
            session.log("exco current="+std::to_string(current)+" next="+std::to_string(next));
        };
        excoUpdate(1,1,epoch,header.encoded);
        Bytes rootState(stateBytes,0); double one=1; std::memcpy(rootState.data()+48,&one,8);std::memcpy(rootState.data()+104,&epoch,8);
        session.latest[root]=values(session.reference,{{"name",unicode(rootName)},{"parent_name",unicode("")},{"state",rootState}});
        session.ambassador->updateAttributeValues(root,session.latest[root],rti::VariableLengthData());
        // Diagnostic: the second ExCO update that a SpaceFOM Master sends
        // after the root reference frame publication, before the peer achieves
        // root_frame_discovered (SISO-STD-018-2020 figure 7-6).
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
        // Diagnostic: repeat the initial data inside the multiphase initialization
        // window, as a SpaceFOM Master does with send_init_data.
        session.ambassador->updateAttributeValues(root,session.latest[root],rti::VariableLengthData());
        session.ambassador->updateAttributeValues(vessel,session.latest[vessel],rti::VariableLengthData());
        for(size_t j=0;j<bodies.size();++j)
            session.ambassador->updateAttributeValues(bodies[j],session.latest[bodies[j]],rti::VariableLengthData());
        session.barrier("initialization_started");
        session.registerSync("initialization_completed");
        session.timeManagement();
        excoUpdate(1,2,epoch);session.barrier("mtr_run",true);excoUpdate(2,2,epoch);session.log("run");
        const int32_t freeze=header.count/2;
        for(int32_t i=1;i<header.count;++i) {
            // Master-scheduled freezes are announced one second ahead so every federate can schedule the target.
            if(masterModes && i==freeze-std::min<int32_t>(64,freeze-1)) excoUpdate(2,3,epoch+static_cast<double>(freeze)/64.0);
            if(i==freeze && !masterModes) {session.expectRequest(3);excoUpdate(2,3,epoch+static_cast<double>(i)/64.0);}
            publishFrame(i,true); session.advance(static_cast<int64_t>(i)*stepUs);
            if(i==freeze) {
                session.barrier("mtr_freeze",true);excoUpdate(3,3,epoch+static_cast<double>(i)/64.0);session.log("freeze");
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
