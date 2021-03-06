# Sweep to evaluate the sensitivity of each design to mission range

import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/../..'))

import numpy as np
from gpkit import Model, ureg
from matplotlib import pyplot as plt
from aircraft_models import OnDemandAircraft 
from aircraft_models import OnDemandSizingMission, OnDemandRevenueMission
from aircraft_models import OnDemandDeadheadMission, OnDemandMissionCost
from study_input_data import generic_data, configuration_data
from collections import OrderedDict
from noise_models import vortex_noise


# Delete certain configurations
configs = configuration_data.copy()
del configs["Tilt duct"]
del configs["Autogyro"]
del configs["Helicopter"]
del configs["Coaxial heli"]
del configs["Multirotor"]

#Optimize remaining configurations
for config in configs:

	print "Solving configuration: " + config

	#set up range arrays (different for each configuration)
	num_pts_short = 4
	num_pts_long = 9
	
	if (config == "Multirotor"):
		mission_range_array = np.linspace(1,18,num_pts_short)
	elif (config == "Helicopter"):
		mission_range_array = np.linspace(2,36,num_pts_short)
	elif (config == "Coaxial heli"):
		mission_range_array = np.linspace(1,49,num_pts_short)
	elif (config == "Compound heli"):
		mission_range_array = np.linspace(10,82,num_pts_long)
	elif (config == "Lift + cruise"):
		mission_range_array = np.linspace(10,85,num_pts_long)
	elif (config == "Tilt wing"):
		mission_range_array = np.linspace(15,98,num_pts_long)
	elif (config == "Tilt rotor"):
		mission_range_array = np.linspace(15,120,num_pts_long)
		
	mission_range_array = mission_range_array*ureg.nautical_mile

	c = configs[config]

	configs[config]["TOGW"] = np.zeros(np.size(mission_range_array))
	configs[config]["W_{battery}"] = np.zeros(np.size(mission_range_array))
	configs[config]["cost_per_seat_mile"] = np.zeros(np.size(mission_range_array))
	configs[config]["SPL_A"] = np.zeros(np.size(mission_range_array))

	for i,mission_range in enumerate(mission_range_array):
		
		sizing_mission_range = mission_range
		revenue_mission_range = mission_range
		deadhead_mission_range = mission_range
	
		problem_subDict = {}
	
		Aircraft = OnDemandAircraft(autonomousEnabled=generic_data["autonomousEnabled"])
		problem_subDict.update({
			Aircraft.L_D_cruise: c["L/D"], #estimated L/D in cruise
			Aircraft.eta_cruise: generic_data["\eta_{cruise}"], #propulsive efficiency in cruise
			Aircraft.tailRotor_power_fraction_hover: c["tailRotor_power_fraction_hover"],
			Aircraft.tailRotor_power_fraction_levelFlight: c["tailRotor_power_fraction_levelFlight"],
			Aircraft.cost_per_weight: generic_data["vehicle_cost_per_weight"], #vehicle cost per unit empty weight
			Aircraft.battery.C_m: generic_data["C_m"], #battery energy density
			Aircraft.battery.cost_per_C: generic_data["battery_cost_per_C"], #battery cost per unit energy capacity
			Aircraft.rotors.N: c["N"], #number of propellers
			Aircraft.rotors.Cl_mean_max: c["Cl_{mean_{max}}"], #maximum allowed mean lift coefficient
			Aircraft.structure.weight_fraction: c["weight_fraction"], #empty weight fraction
			Aircraft.electricalSystem.eta: generic_data["\eta_{electric}"], #electrical system efficiency	
		})

		SizingMission = OnDemandSizingMission(Aircraft,mission_type=generic_data["sizing_mission"]["type"],
			reserve_type=generic_data["reserve_type"])
		problem_subDict.update({
			SizingMission.mission_range: sizing_mission_range,#mission range
			SizingMission.V_cruise: c["V_{cruise}"],#cruising speed
			SizingMission.t_hover: generic_data["sizing_mission"]["t_{hover}"],#hover time
			SizingMission.T_A: c["T/A"],#disk loading
			SizingMission.passengers.N_passengers: generic_data["sizing_mission"]["N_{passengers}"],#Number of passengers
		})

		RevenueMission = OnDemandRevenueMission(Aircraft,mission_type=generic_data["revenue_mission"]["type"])
		problem_subDict.update({
			RevenueMission.mission_range: revenue_mission_range,#mission range
			RevenueMission.V_cruise: c["V_{cruise}"],#cruising speed
			RevenueMission.t_hover: generic_data["revenue_mission"]["t_{hover}"],#hover time
			RevenueMission.passengers.N_passengers: generic_data["revenue_mission"]["N_{passengers}"],#Number of passengers
			RevenueMission.time_on_ground.charger_power: generic_data["charger_power"], #Charger power
		})

		DeadheadMission = OnDemandDeadheadMission(Aircraft,mission_type=generic_data["deadhead_mission"]["type"])
		problem_subDict.update({
			DeadheadMission.mission_range: deadhead_mission_range,#mission range
			DeadheadMission.V_cruise: c["V_{cruise}"],#cruising speed
			DeadheadMission.t_hover: generic_data["deadhead_mission"]["t_{hover}"],#hover time
			DeadheadMission.passengers.N_passengers: generic_data["deadhead_mission"]["N_{passengers}"],#Number of passengers
			DeadheadMission.time_on_ground.charger_power: generic_data["charger_power"], #Charger power
		})

		MissionCost = OnDemandMissionCost(Aircraft,RevenueMission,DeadheadMission)
		problem_subDict.update({
			MissionCost.revenue_mission_costs.operating_expenses.pilot_cost.wrap_rate: generic_data["pilot_wrap_rate"],#pilot wrap rate
			MissionCost.revenue_mission_costs.operating_expenses.maintenance_cost.wrap_rate: generic_data["mechanic_wrap_rate"], #mechanic wrap rate
			MissionCost.revenue_mission_costs.operating_expenses.maintenance_cost.MMH_FH: generic_data["MMH_FH"], #maintenance man-hours per flight hour
			MissionCost.deadhead_mission_costs.operating_expenses.pilot_cost.wrap_rate: generic_data["pilot_wrap_rate"],#pilot wrap rate
			MissionCost.deadhead_mission_costs.operating_expenses.maintenance_cost.wrap_rate: generic_data["mechanic_wrap_rate"], #mechanic wrap rate
			MissionCost.deadhead_mission_costs.operating_expenses.maintenance_cost.MMH_FH: generic_data["MMH_FH"], #maintenance man-hours per flight hour
			MissionCost.deadhead_ratio: generic_data["deadhead_ratio"], #deadhead ratio
		})

		problem = Model(MissionCost["cost_per_trip"],
			[Aircraft, SizingMission, RevenueMission, DeadheadMission, MissionCost])
		problem.substitutions.update(problem_subDict)
		solution = problem.solve(verbosity=0)
		configs[config]["solution"] = solution

		if i == 0:
			num_segments = len(solution("P_{battery}_OnDemandSizingMission"))
			configs[config]["P_{battery}"] = np.zeros((np.size(mission_range_array),num_segments))

		configs[config]["TOGW"][i] = solution("TOGW_OnDemandAircraft").to(ureg.lbf).magnitude
		configs[config]["W_{battery}"][i] = solution("W_OnDemandAircraft/Battery").to(ureg.lbf).magnitude
		configs[config]["cost_per_seat_mile"][i] = solution("cost_per_seat_mile_OnDemandMissionCost").to(ureg.mile**-1).magnitude
		configs[config]["P_{battery}"][i] = solution("P_{battery}_OnDemandSizingMission").to(ureg.kW).magnitude

		#Noise computations
		T_perRotor = solution("T_perRotor_OnDemandSizingMission")[0]
		Q_perRotor = solution("Q_perRotor_OnDemandSizingMission")[0]
		R = solution("R")
		VT = solution("VT_OnDemandSizingMission")[0]
		s = solution("s")
		Cl_mean = solution("Cl_{mean_{max}}")
		N = solution("N")

		B = generic_data["B"]
		delta_S = generic_data["delta_S"]

		#A-weighted
		f_peak, SPL, spectrum = vortex_noise(T_perRotor=T_perRotor,R=R,VT=VT,s=s,
			Cl_mean=Cl_mean,N=N,B=B,delta_S=delta_S,h=0*ureg.ft,t_c=0.12,St=0.28,
			weighting="A")
		configs[config]["SPL_A"][i] = SPL
		
	configs[config]["mission_range"] = mission_range_array
	configs[config]["TOGW"] = configs[config]["TOGW"]*ureg.lbf
	configs[config]["W_{battery}"] = configs[config]["W_{battery}"]*ureg.lbf
	configs[config]["cost_per_seat_mile"] = configs[config]["cost_per_seat_mile"]*ureg.mile**-1
	configs[config]["P_{battery}"] = configs[config]["P_{battery}"]*ureg.kW


# Plotting commands
plt.ion()
fig1 = plt.figure(figsize=(12,12), dpi=80)
plt.show()

style = {}
style["linestyle"] = ["-","-","-","-","--","--","--","--"]
style["marker"] = ["s","o","^","v","s","o","^","v"]
style["fillstyle"] = ["full","full","full","full","none","none","none","none"]
style["markersize"] = 10

#Maximum takeoff weight
plt.subplot(2,2,1)
for i, config in enumerate(configs):
	c = configs[config]
	plt.plot(c["mission_range"].to(ureg.nautical_mile).magnitude,c["TOGW"].to(ureg.lbf).magnitude,
		color="black",linewidth=1.5,linestyle=style["linestyle"][i],marker=style["marker"][i],
		fillstyle=style["fillstyle"][i],markersize=style["markersize"],label=config)
plt.grid()
plt.ylim(ymin=0)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.xlabel('Mission range (nmi)', fontsize = 16)
plt.ylabel('Weight (lbf)', fontsize = 16)
plt.title("Takeoff Gross Weight",fontsize = 20)
plt.legend(numpoints = 1,loc='lower right', fontsize = 12, framealpha=1)

#Battery weight
plt.subplot(2,2,2)
for i, config in enumerate(configs):
	c = configs[config]
	plt.plot(c["mission_range"].to(ureg.nautical_mile).magnitude,c["W_{battery}"].to(ureg.lbf).magnitude,
		color="black",linewidth=1.5,linestyle=style["linestyle"][i],marker=style["marker"][i],
		fillstyle=style["fillstyle"][i],markersize=style["markersize"],label=config)
plt.grid()
plt.ylim(ymin=0)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.xlabel('Mission range (nmi)', fontsize = 16)
plt.ylabel('Weight (lbf)', fontsize = 16)
plt.title("Battery Weight",fontsize = 20)
plt.legend(numpoints = 1,loc='lower right', fontsize = 12, framealpha=1)

#Trip cost per seat mile
plt.subplot(2,2,3)
for i, config in enumerate(configs):
	c = configs[config]
	plt.plot(c["mission_range"].to(ureg.nautical_mile).magnitude,
		c["cost_per_seat_mile"].to(ureg.mile**-1).magnitude,
		color="black",linewidth=1.5,linestyle=style["linestyle"][i],marker=style["marker"][i],
		fillstyle=style["fillstyle"][i],markersize=style["markersize"],label=config)
plt.grid()
plt.ylim(ymin=0)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.xlabel('Mission range (nmi)', fontsize = 16)
plt.ylabel('Cost ($US/mile)', fontsize = 16)
plt.title("Cost per Seat Mile",fontsize = 20)
plt.legend(numpoints = 1,loc='lower right', fontsize = 12, framealpha=1)

#Sound pressure level (in hover)
plt.subplot(2,2,4)
for i, config in enumerate(configs):
	c = configs[config]
	plt.plot(c["mission_range"].to(ureg.nautical_mile).magnitude,c["SPL_A"],
		color="black",linewidth=1.5,linestyle=style["linestyle"][i],marker=style["marker"][i],
		fillstyle=style["fillstyle"][i],markersize=style["markersize"],label=config)
plt.grid()
plt.ylim(ymin=55)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.xlabel('Mission range (nmi)', fontsize = 16)
plt.ylabel('SPL (dBA)', fontsize = 16)
plt.title("Sound Pressure Level in Hover",fontsize = 20)
plt.legend(numpoints = 1,loc='lower right', fontsize = 12, framealpha=1)

if generic_data["reserve_type"] == "FAA_aircraft" or generic_data["reserve_type"] == "FAA_heli":
	num = solution("t_{loiter}_OnDemandSizingMission").to(ureg.minute).magnitude
	if generic_data["reserve_type"] == "FAA_aircraft":
		reserve_type_string = "FAA aircraft VFR (%0.0f-minute loiter time)" % num
	elif generic_data["reserve_type"] == "FAA_heli":
		reserve_type_string = "FAA helicopter VFR (%0.0f-minute loiter time)" % num
elif generic_data["reserve_type"] == "Uber":
	num = solution["constants"]["R_{divert}_OnDemandSizingMission"].to(ureg.nautical_mile).magnitude
	reserve_type_string = " (%0.0f-nm diversion distance)" % num

if generic_data["autonomousEnabled"]:
	autonomy_string = "autonomy enabled"
else:
	autonomy_string = "pilot required"

title_str = "Aircraft parameters: battery energy density = %0.0f Wh/kg; %0.0f rotor blades; %s\n" \
	% (generic_data["C_m"].to(ureg.Wh/ureg.kg).magnitude, B, autonomy_string) \
	+ "Sizing mission (%s): %0.0f passengers; %0.0fs hover time; reserve type = " \
	% (generic_data["sizing_mission"]["type"],\
	 generic_data["sizing_mission"]["N_{passengers}"], generic_data["sizing_mission"]["t_{hover}"].to(ureg.s).magnitude)\
	+ reserve_type_string + "\n"\
	+ "Revenue mission (%s): same range as sizing mission; %0.1f passengers; %0.0fs hover time; no reserve; charger power = %0.0f kW\n" \
	% (generic_data["revenue_mission"]["type"],\
	 generic_data["revenue_mission"]["N_{passengers}"], generic_data["revenue_mission"]["t_{hover}"].to(ureg.s).magnitude,\
	 generic_data["charger_power"].to(ureg.kW).magnitude) \
	+ "Deadhead mission (%s): same range as sizing mission; %0.1f passengers; %0.0fs hover time; no reserve; deadhead ratio = %0.1f" \
	% (generic_data["deadhead_mission"]["type"],\
	 generic_data["deadhead_mission"]["N_{passengers}"], generic_data["deadhead_mission"]["t_{hover}"].to(ureg.s).magnitude,\
	 generic_data["deadhead_ratio"])

plt.suptitle(title_str,fontsize = 13)
plt.tight_layout()
plt.subplots_adjust(left=0.08,right=0.98,bottom=0.05,top=0.87)
plt.savefig('mission_range_plot_01.pdf')