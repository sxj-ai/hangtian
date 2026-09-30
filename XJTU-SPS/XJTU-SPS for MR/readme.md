
1: Fast Charging, Sunlit Area, No Task;

2: Shunt, Sunlit Area, Non-orientation Task 1;

3: Trickle Charging, Sunlit Area, No Task;

4: Joint Power Supply, Sunlit Area, Ground-orientation Task 2;

5: Idle, Shadow Area, No Task;

6: Discharge, Shadow Area, Non-orientation Task 3;




Specifically, 

(1) Label 1 corresponds to the fast charging condition. Characteristics: the SA output power is large, the BAT experiences a very short constant current (CC) charging followed by an immediate transition to constant voltage (CV) charging state, and the LOAD power is small;

(2) Label 2 corresponds to the shunt condition. Characteristics: the SA output power capability is greater than the sum of LOAD and BAT charging demand, the shunt regulator shunts a large current or the MPPT (Maximum Power Point Tracking) algorithm operates at a non-maximum power point;

(3) Label 3 corresponds to the trickle charging condition. Characteristics: the BAT charging current is small, which compensates for the self-discharge loss of the BAT and maintains a full charge state;

(4) Label 4 corresponds to the joint power supply condition. Characteristics: the SA output power is large, the BAT discharge current is large, and the LOAD power is large;

(5) Label 5 corresponds to the idle condition. Characteristics: no power output from SA, small BAT charge/discharge current, and small LOAD power;

(6) Label 6 corresponds to the discharge condition. Characteristics: no power output from SA, large BAT discharge current, and large LOAD power.

In our published XJTU-SPS dataset, based on the operational characteristics of the power system, we preliminarily classify the conditions into 6 categories. Users can further refine the condition classification according to their actual research needs, such as distinguishing between CC and CV charging, or strictly distinguishing between trickle charging and the late stage of CV charging when it is about to be fully charged based on a strict power thresholds.