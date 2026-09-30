#ifndef QUALIFICATION_TRICKHLA_LOGGING_SPACEFOM_HH
#define QUALIFICATION_TRICKHLA_LOGGING_SPACEFOM_HH

#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

#include "SpaceFOM/PhysicalEntity.hh"
#include "SpaceFOM/RefFrameState.hh"
#include "SpaceFOM/SpaceTimeCoordinateData.hh"

// Per-update logging override for the 2207 interoperability test.
//
// The prototypes publish one state per object per tick and our least common
// time step is 15,625 microseconds. These derived packings call the stock
// unpack() and then print the object name, the HLA logical time derived from
// the state time tag, and the fourteen decoded state values whenever a new
// update changes the state time. The stream uses seventeen significant digits,
// which round-trips binary64, so the printed values can be compared bit for
// bit with the published recording.
//
// The apply-logging-override.sh script in this directory copies this header
// into the TrickHLA include tree and switches the two packings in
// S_modules/SpaceFOM/RefFrame.sm and S_modules/SpaceFOM/PhysicalEntity.sm to
// these classes, then the simulation is rebuilt.

inline void interop_log_state(
   std::string const &name,
   SpaceFOM::SpaceTimeCoordinateData const &state )
{
   static const double epoch_tt = 7529673600.00018;
   // Log only states inside the recording's time window. An update without
   // state carries a sentinel time (for example -DBL_MAX); multiplying it
   // would overflow, which Trick traps as a floating-point exception.
   if ( !std::isfinite( state.time ) || state.time < epoch_tt || state.time > epoch_tt + 1.0e6 ) {
      return;
   }
   long long tick = static_cast<long long>( std::llround( ( state.time - epoch_tt ) * 64.0 ) );

   std::ostringstream line;
   line << std::setprecision( 17 );
   line << "INTEROP object=" << name
        << " tick=" << tick
        << " hla_time_us=" << tick * 15625
        << " time=" << state.time
        << " pos=" << state.pos[0] << "," << state.pos[1] << "," << state.pos[2]
        << " vel=" << state.vel[0] << "," << state.vel[1] << "," << state.vel[2]
        << " quat=" << state.att.scalar
        << "," << state.att.vector[0] << "," << state.att.vector[1] << "," << state.att.vector[2]
        << " ang_vel=" << state.ang_vel[0] << "," << state.ang_vel[1] << "," << state.ang_vel[2];

   std::cout << line.str() << std::endl;
}

class LoggingRefFrameState : public SpaceFOM::RefFrameState {
 public:
   explicit LoggingRefFrameState( SpaceFOM::RefFrameData &data )
      : SpaceFOM::RefFrameState( data )
   {
   }

   void unpack() override
   {
      SpaceFOM::RefFrameState::unpack();
      if ( packing_data.state.time != last_time ) {
         last_time = packing_data.state.time;
         interop_log_state( packing_data.name, packing_data.state );
      }
   }

 private:
   double last_time = -1.0;
};

class LoggingPhysicalEntity : public SpaceFOM::PhysicalEntity {
 public:
   explicit LoggingPhysicalEntity( SpaceFOM::PhysicalEntityData &data )
      : SpaceFOM::PhysicalEntity( data )
   {
   }

   void unpack() override
   {
      SpaceFOM::PhysicalEntity::unpack();
      if ( pe_packing_data.state.time != last_time ) {
         last_time = pe_packing_data.state.time;
         interop_log_state( pe_packing_data.name, pe_packing_data.state );
      }
   }

 private:
   double last_time = -1.0;
};

#endif // QUALIFICATION_TRICKHLA_LOGGING_SPACEFOM_HH
