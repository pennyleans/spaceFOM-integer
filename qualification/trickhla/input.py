##############################################################################
# PURPOSE:
#    TrickHLA SpaceFOM federate configured as the "other" role to join the
#    2207 exchange federation. It joins as a plain observer: it is not the
#    Master, not the Pacing federate and not the Root Reference Frame
#    Publisher, and it subscribes to the root frame, one body frame and the
#    orbital_vessel PhysicalEntity published by our publisher.
#
# REFERENCE:
#    SISO-STD-018-2020. TrickHLA revision 9faa0c5e547acb2596047c9bb875cb34ccb0fa2a.
#    Modelled on sims/SpaceFOM/SIM_Entity_Test/RUN_PE/input.py.
#
# ASSUMPTIONS AND LIMITATIONS:
#    ((The sim must define root_ref_frame, leaf_ref_frame, physical_entity and
#      the THLA SimObjects, as SIM_Entity_Test does.)
#     (The stock sim defines only two reference frame packings, so this file
#      subscribes to the root frame and body_10; a complete subscription to all
#      eleven body frames needs one additional frame packing per body.)
#     (Per-update decoding of the fourteen state values requires overriding the
#      SpaceFOM packing unpack() methods in C++; the configuration here turns on
#      the TrickHLA trace logging instead.)
#     (The Pitch pRTI Free edition admits at most two federates, so this
#      federate cannot join a federation that already has our publisher and
#      observer. The three-federate exchange was not run.))
##############################################################################
import sys
sys.path.append( '../../../' )

from TrickHLA_data.SpaceFOM.SpaceFOMFederateConfig import *
from TrickHLA_data.SpaceFOM.SpaceFOMRefFrameObject import *
from TrickHLA_data.SpaceFOM.SpaceFOMPhysicalEntityObject import *


def print_usage_message():

   print( ' ' )
   print( 'TrickHLA interop observer command line options:' )
   print( '  -h --help              : Print this help message.' )
   print( '  -f --fed_name [name]   : Federate name, default orbital_other.' )
   print( '  -fe --fex_name [name]  : Federation execution name, default orbital_8989.' )
   print( '  --crc_host [host]      : CRC host, default localhost.' )
   print( '  --crc_port [port]      : CRC port, default 8989.' )
   print( '  -s --stop [time]       : Stop time in seconds, default 65.0.' )
   print( '  --verbose [on|off]     : Show verbose messages, default off.' )
   print( ' ' )

   trick.exec_terminate_with_return( -1,
                                     sys._getframe( 0 ).f_code.co_filename,
                                     sys._getframe( 0 ).f_lineno,
                                     'Print usage message.' )
   return


def parse_command_line():

   global print_usage
   global run_duration
   global verbose
   global federate_name
   global federation_name
   global crc_host
   global crc_port

   argc = trick.command_line_args_get_argc()
   argv = trick.command_line_args_get_argv()

   index = 2
   while ( index < argc ):

      if ( ( str( argv[index] ) == '-h' ) | ( str( argv[index] ) == '--help' ) ):
         print_usage = True

      elif ( ( str( argv[index] ) == '-f' ) | ( str( argv[index] ) == '--fed_name' ) ):
         index = index + 1
         if ( index < argc ):
            federate_name = str( argv[index] )
         else:
            print( 'ERROR: Missing --fed_name [name] argument.' )
            print_usage = True

      elif ( ( str( argv[index] ) == '-fe' ) | ( str( argv[index] ) == '--fex_name' ) ):
         index = index + 1
         if ( index < argc ):
            federation_name = str( argv[index] )
         else:
            print( 'ERROR: Missing --fex_name [name] argument.' )
            print_usage = True

      elif ( str( argv[index] ) == '--crc_host' ):
         index = index + 1
         if ( index < argc ):
            crc_host = str( argv[index] )
         else:
            print( 'ERROR: Missing --crc_host [host] argument.' )
            print_usage = True

      elif ( str( argv[index] ) == '--crc_port' ):
         index = index + 1
         if ( index < argc ):
            crc_port = str( argv[index] )
         else:
            print( 'ERROR: Missing --crc_port [port] argument.' )
            print_usage = True

      elif ( ( str( argv[index] ) == '-s' ) | ( str( argv[index] ) == '--stop' ) ):
         index = index + 1
         if ( index < argc ):
            run_duration = float( str( argv[index] ) )
         else:
            print( 'ERROR: Missing -s [time] argument.' )
            print_usage = True

      elif ( str( argv[index] ) == '--verbose' ):
         index = index + 1
         if ( index < argc ):
            if ( str( argv[index] ) == 'on' ):
               verbose = True
            elif ( str( argv[index] ) == 'off' ):
               verbose = False
            else:
               print( 'ERROR: Unknown --verbose argument: ' + str( argv[index] ) )
               print_usage = True
         else:
            print( 'ERROR: Missing --verbose [on|off] argument.' )
            print_usage = True

      elif ( ( str( argv[index] ) == '-d' ) ):
         break

      else:
         print( 'ERROR: Unknown command line argument ' + str( argv[index] ) )
         print_usage = True

      index = index + 1
   return


print_usage = False
run_duration = 65.0
verbose = False
federate_name = 'orbital_other'
federation_name = 'orbital_8989'
crc_host = 'localhost'
crc_port = '8989'

parse_command_line()

if ( print_usage == True ):
   print_usage_message()

#--------------------------------------------------------------------------
# Trick executive parameters.
#--------------------------------------------------------------------------
trick.exec_set_trap_sigfpe( True )
trick.exec_set_enable_freeze( False )
trick.exec_set_freeze_command( False )
trick.sim_control_panel_set_enabled( False )
trick.exec_set_stack_trace( False )

#--------------------------------------------------------------------------
# Set up the HLA interfaces.
#--------------------------------------------------------------------------
federate = SpaceFOMFederateConfig(
   THLA.federate,
   THLA.manager,
   THLA.execution_control,
   THLA.ExCO,
   federation_name,
   federate_name,
   True )

if ( verbose == True ):
   federate.set_debug_level( trick.TrickHLA.DEBUG_LEVEL_6_TRACE )
   federate.set_debug_source( trick.TrickHLA.DEBUG_SOURCE_ALL_MODULES )
else:
   federate.set_debug_level( trick.TrickHLA.DEBUG_LEVEL_0_TRACE )

#--------------------------------------------------------------------------
# This federate is the "other" role: no Master, Pacing or RRFP role.
#--------------------------------------------------------------------------
federate.set_master_role( False )
federate.set_pacing_role( False )
federate.set_RRFP_role( False )

#--------------------------------------------------------------------------
# Required federates set by our publisher.
#--------------------------------------------------------------------------
federate.add_known_federate( True, str( federate.federate.name ) )
federate.add_known_federate( True, 'orbital_master' )
federate.add_known_federate( True, 'orbital_observer' )

#--------------------------------------------------------------------------
# Pitch pRTI local settings designator.
#--------------------------------------------------------------------------
THLA.federate.local_settings = 'crcHost = ' + crc_host + '\n crcPort = ' + crc_port

#--------------------------------------------------------------------------
# Time management parameters. Our publisher sets a least common time step of
# 15625 microseconds and a matching lookahead, so the federate software frame
# must be a multiple of 0.015625 seconds.
#--------------------------------------------------------------------------
federate.set_lookahead_time( 0.015625 )
trick.exec_set_software_frame( 0.015625 )
trick.exec_set_freeze_frame( 0.015625 )
federate.set_time_regulating( True )
federate.set_time_constrained( True )

#---------------------------------------------------------------------------
# Root reference frame subscription. The publisher is the RRFP.
#---------------------------------------------------------------------------
root_frame = SpaceFOMRefFrameObject(
   create_frame_object          = False,
   frame_instance_name          = 'SolarSystemBarycentricInertial',
   frame_S_define_instance      = root_ref_frame.frame_packing,
   frame_S_define_instance_name = 'root_ref_frame.frame_packing',
   frame_conditional            = root_ref_frame.conditional )

root_ref_frame.frame_packing.debug = verbose
federate.set_root_frame( root_frame )

#---------------------------------------------------------------------------
# One body reference frame subscription. See the limitations above.
#---------------------------------------------------------------------------
body_frame = SpaceFOMRefFrameObject(
   create_frame_object          = False,
   frame_instance_name          = 'body_10',
   frame_S_define_instance      = leaf_ref_frame.frame_packing,
   frame_S_define_instance_name = 'leaf_ref_frame.frame_packing',
   parent_S_define_instance     = root_ref_frame.frame_packing,
   parent_name                  = 'SolarSystemBarycentricInertial',
   frame_conditional            = leaf_ref_frame.conditional,
   frame_lag_comp               = leaf_ref_frame.lag_compensation,
   frame_ownership              = leaf_ref_frame.ownership_handler,
   frame_deleted                = leaf_ref_frame.deleted_callback )

leaf_ref_frame.frame_packing.debug = verbose
federate.add_fed_object( body_frame )
leaf_ref_frame.lag_compensation.set_integ_tolerance( 1.0e-6 )
leaf_ref_frame.lag_compensation.set_integ_dt( 0.025 )
body_frame.set_lag_comp_type( trick.TrickHLA.LAG_COMPENSATION_RECEIVE_SIDE )

#---------------------------------------------------------------------------
# orbital_vessel PhysicalEntity subscription.
#---------------------------------------------------------------------------
vessel = SpaceFOMPhysicalEntityObject(
   create_entity_object          = False,
   entity_instance_name          = 'orbital_vessel',
   entity_S_define_instance      = physical_entity.entity_packing,
   entity_S_define_instance_name = 'physical_entity.entity_packing',
   entity_conditional            = physical_entity.conditional,
   entity_lag_comp               = physical_entity.lag_compensation,
   entity_ownership              = physical_entity.ownership_handler,
   entity_deleted                = physical_entity.deleted_callback )

physical_entity.entity_packing.debug = verbose
federate.add_fed_object( vessel )
physical_entity.lag_compensation.set_integ_tolerance( 1.0e-6 )
physical_entity.lag_compensation.set_integ_dt( 0.025 )
vessel.set_lag_comp_type( trick.TrickHLA.LAG_COMPENSATION_RECEIVE_SIDE )

#---------------------------------------------------------------------------
# Add the HLA SimObjects associated with this federate.
#---------------------------------------------------------------------------
federate.add_sim_object( THLA )
federate.add_sim_object( THLA_INIT )
federate.add_sim_object( root_ref_frame )
federate.add_sim_object( leaf_ref_frame )
federate.add_sim_object( physical_entity )

#---------------------------------------------------------------------------
# Initialize the federate configuration object.
#---------------------------------------------------------------------------
federate.initialize()

#---------------------------------------------------------------------------
# Simulation termination time.
#---------------------------------------------------------------------------
if run_duration:
   trick.sim_services.exec_set_terminate_time( run_duration )
