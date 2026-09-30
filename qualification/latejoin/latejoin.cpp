// Joins a running exchange after initialization and follows the SpaceFOM late-joiner steps that TrickHLA uses:
// detect the pending initialization_completed point, request the ExCO, and wait for its values.
#include "../../native/spacefom/transport.hpp"
using namespace sf;

class LateJoiner final : public Session {
public:
    std::map<std::string,size_t> reflections;
    std::set<std::wstring> achieved;
    std::string rootFrame; int16_t current=-1,next=-1; bool excoReceived=false,rootReceived=false;
    void reflect(rti::ObjectInstanceHandle object,const rti::AttributeHandleValueMap& attrs) {
        auto name=objectNames.find(object); if(name==objectNames.end()) return;
        ++reflections[name->second];
        if(name->second=="ExCO" && attrs.count(exco.at("root_frame_name"))) {
            rootFrame=decodeUnicode(bytes(attrs.at(exco.at("root_frame_name"))));
            current=little<int16_t>(bytes(attrs.at(exco.at("current_execution_mode"))).data());
            next=little<int16_t>(bytes(attrs.at(exco.at("next_execution_mode"))).data());excoReceived=true;
        }
        if(name->second==rootName && attrs.count(reference.at("name"))) rootReceived=true;
    }
    void reflectAttributeValues(rti::ObjectInstanceHandle o,const rti::AttributeHandleValueMap& a,const rti::VariableLengthData&,rti::OrderType,rti::TransportationType,rti::SupplementalReflectInfo) override {reflect(o,a);}
    void reflectAttributeValues(rti::ObjectInstanceHandle o,const rti::AttributeHandleValueMap& a,const rti::VariableLengthData&,rti::OrderType,rti::TransportationType,const rti::LogicalTime&,rti::OrderType,rti::SupplementalReflectInfo) override {reflect(o,a);}
    void reflectAttributeValues(rti::ObjectInstanceHandle o,const rti::AttributeHandleValueMap& a,const rti::VariableLengthData&,rti::OrderType,rti::TransportationType,const rti::LogicalTime&,rti::OrderType,rti::MessageRetractionHandle,rti::SupplementalReflectInfo) override {reflect(o,a);}
    // Achieves every announced point except the two the Master leaves pending, as a SpaceFOM late joiner does.
    void service() override {
        for(const auto& label:announced)
            if(label!=L"initialization_completed" && label!=L"mtr_shutdown" && achieved.insert(label).second) {
                ambassador->synchronizationPointAchieved(label); log("achieved "+narrow(label));
            }
    }
    rti::ObjectInstanceHandle find(const std::string& target) {
        for(const auto& entry:objectNames) if(entry.second==target) return entry.first;
        throw std::runtime_error("object not discovered: "+target);
    }
};

int main(int argc,char** argv) {
    try {
        require(argc==3,"usage: latejoin rti://127.0.0.1:port federation");
        LateJoiner session; session.connect(argv[1],argv[2]);
        session.wait([&]{try {session.ambassador->joinFederationExecution(L"orbital_late_probe",L"spacefom_late_join_probe",session.federation);return true;}catch(const rti::FederationExecutionDoesNotExist&){std::this_thread::sleep_for(std::chrono::milliseconds(20));return false;}},"federation");
        session.log("joined");
        session.handles();
        session.ambassador->subscribeObjectClassAttributes(session.exco.handle,session.exco.set());
        session.ambassador->subscribeObjectClassAttributes(session.reference.handle,session.reference.set());
        session.ambassador->subscribeObjectClassAttributes(session.entity.handle,session.entity.set());
        session.wait([&]{return session.announced.count(L"initialization_completed")!=0 || session.announced.count(L"initialization_started")!=0;},"role determination");
        bool late=session.announced.count(L"initialization_completed")!=0;
        session.log(late?"late_joiner_determined":"early_joiner_determined");
        require(late,"joined before initialization completed; start the probe later");
        session.wait([&]{std::set<std::string> n;for(const auto& o:session.objectNames)n.insert(o.second);return n.count("ExCO")&&n.count(rootName);},"ExCO and root discovery");
        session.ambassador->requestAttributeValueUpdate(session.find("ExCO"),session.exco.set(),rti::VariableLengthData());
        session.log("requested ExCO");
        session.wait([&]{return session.excoReceived;},"ExCO update");
        session.log("ExCO root="+session.rootFrame+" current="+std::to_string(session.current)+" next="+std::to_string(session.next));
        session.ambassador->requestAttributeValueUpdate(session.find(rootName),session.reference.set(),rti::VariableLengthData());
        session.wait([&]{return session.rootReceived;},"root frame update");
        session.log("root frame received");
        auto until=std::chrono::steady_clock::now()+std::chrono::milliseconds(500);
        while(std::chrono::steady_clock::now()<until) session.pump();
        size_t vessel=session.reflections["orbital_vessel"];
        session.finish();
        std::cout<<"{\"late_joiner\":true,\"exco_received\":true,\"root_frame\":\""<<session.rootFrame<<"\",\"exco_current_mode\":"<<session.current
                 <<",\"exco_next_mode\":"<<session.next<<",\"root_frame_received\":true,\"vessel_updates_seen\":"<<vessel<<"}"<<std::endl;
        return 0;
    } catch(const rti::Exception& e) {std::wcerr<<L"RTI failure: "<<e.what()<<std::endl;}
      catch(const std::exception& e) {std::cerr<<"failure: "<<e.what()<<std::endl;}
    return 1;
}
