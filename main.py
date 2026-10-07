import random

import streamlit as st

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None
    ttk = None




PROCESSING_TIME = 19800   # 5.5 小時 = 19800 秒

ROBOT_ACTION_TIME = 10

ROBOT_MOVE_TIME = 6

CONVEYOR_TIME = 15

RAW_TRANSPORT_TIME = 50    

RAW_GEN_INTERVAL = 90     # 每 90 秒生成 1 個 Raw



class Slot:

    def __init__(self, slot_id):

        self.slot_id = slot_id

        self.state = "EMPTY"  # EMPTY, PROCESSING, GOOD, FAILED

        self.timer = 0

        self.attempt = 0



class Machine:

    def __init__(self, name, num_slots=8):

        self.name = name

        self.slots = [Slot(i + 1) for i in range(num_slots)]



    def has_finished(self):

        return any(s.state in ["GOOD", "FAILED"] for s in self.slots)



    def has_empty(self):

        return any(s.state == "EMPTY" for s in self.slots)



    def get_finished_slot(self):

        for s in self.slots:

            if s.state in ["GOOD", "FAILED"]:

                return s

        return None



    def get_empty_slot(self):

        for s in self.slots:

            if s.state == "EMPTY":

                return s

        return None



    def tick(self, delta_sec=1, failure_rate=0.1):

        for s in self.slots:

            if s.state == "PROCESSING":

                s.timer -= delta_sec

                if s.timer <= 0:

                    s.timer = 0

                    s.state = "FAILED" if random.random() < failure_rate else "GOOD"



class FactorySim:

    def __init__(self, num_machines=25, slots_per_machine=8, raw_stock=5, failure_rate=0.1):

        self.machines = [Machine(f"M{i+1}", slots_per_machine) for i in range(num_machines)]

        self.raw_stock = raw_stock

        self.good_sink = 0

        self.scrap_sink = 0

        self.failure_rate = failure_rate

       

        self.robot_hand = None

        self.robot_action = "IDLE"

        self.robot_busy_timer = 0

        self.robot_location = "HOME"

       

        self.sim_seconds = 0

        self.raw_gen_timer = 0

        self.raw_in_transit = []

        self.logs = []



    def log(self, text):

        sim_h = self.sim_seconds / 3600.0

        self.logs.append(f"[{sim_h:05.2f}h] {text}")

        if len(self.logs) > 10:

            self.logs.pop(0)



    def start_robot_action(self, action, target):

        move_time = ROBOT_MOVE_TIME if self.robot_location != target else 0

        self.robot_location = target

        self.robot_action = action

        self.robot_busy_timer = ROBOT_ACTION_TIME + move_time



    def robot_decision_cycle(self):

        if self.robot_busy_timer > 0:

            return



        if self.robot_hand is not None:

            self.handle_item_in_hand()

            return



        # 優先級 1：EXCHANGE

        if self.raw_stock > 0:

            for m in self.machines:

                if m.has_finished():

                    self.execute_exchange(m)

                    return



        # 優先級 2：OUTPUT

        for m in self.machines:

            if m.has_finished():

                self.execute_output(m)

                return



        # 優先級 3：INPUT

        if self.raw_stock > 0:

            for m in self.machines:

                if m.has_empty():

                    self.execute_input(m)

                    return



        self.robot_action = "IDLE (等待機台狀態)"



    def execute_exchange(self, m: Machine):

        self.robot_action = f"EXCHANGE @ {m.name}"

        self.start_robot_action(self.robot_action, m.name)

        self.raw_stock -= 1

       

        slot = m.get_finished_slot()

        taken_item = {"type": slot.state, "attempt": slot.attempt, "from_m": m.name}

       

        slot.state = "PROCESSING"

        slot.timer = PROCESSING_TIME

        slot.attempt = 1

       

        self.log(f"Exchange @ {m.name}: 取出 {taken_item['type']} (a={taken_item['attempt']})，投入新 Raw")

        self.robot_hand = taken_item



    def execute_output(self, m: Machine):

        self.robot_action = f"OUTPUT @ {m.name}"

        self.start_robot_action(self.robot_action, m.name)

       

        slot = m.get_finished_slot()

        taken_item = {"type": slot.state, "attempt": slot.attempt, "from_m": m.name}

        slot.state = "EMPTY"

        slot.timer = 0

        slot.attempt = 0

       

        self.log(f"Output @ {m.name}: 取出 {taken_item['type']} (a={taken_item['attempt']})")

        self.robot_hand = taken_item



    def execute_input(self, m: Machine):

        self.robot_action = f"INPUT @ {m.name}"

        self.start_robot_action(self.robot_action, m.name)

        self.raw_stock -= 1

       

        slot = m.get_empty_slot()

        slot.state = "PROCESSING"

        slot.timer = PROCESSING_TIME

        slot.attempt = 1

        self.log(f"Input @ {m.name}: 投入 Raw 至 Slot {slot.slot_id}")



    def handle_item_in_hand(self):

        item = self.robot_hand



        if item["type"] == "GOOD":

            self.good_sink += 1

            self.robot_action = "GOOD 送往吸收器"

            self.start_robot_action(self.robot_action, "GOOD_SINK")

            self.log(f"吸收器: 接收 GOOD (來自 {item['from_m']})")

            self.robot_hand = None

            return



        if item["type"] == "FAILED":

            if item["attempt"] >= 3:

                self.scrap_sink += 1

                self.robot_action = "FAILED 報廢處置"

                self.start_robot_action(self.robot_action, "SCRAP_SINK")

                self.log(f"報廢區: FAILED 上限處置 (a={item['attempt']})")

                self.robot_hand = None

                return



            self.robot_action = f"REWORK SWAP (HOLD: {item['from_m']} FAILED)"

           

            origin_m = next((m for m in self.machines if m.name == item["from_m"]), None)

            if origin_m and origin_m.has_finished():

                self.swap_with_machine_finished(origin_m, item)

                return



            for m in self.machines:

                if m.has_finished():

                    self.swap_with_machine_finished(m, item)

                    return



            if origin_m and origin_m.has_empty():

                self.put_into_machine_empty(origin_m, item)

                return



            for m in self.machines:

                if m.has_empty():

                    self.put_into_machine_empty(m, item)

                    return



            self.robot_action = "WAIT (重工無可用 Slot)"



    def swap_with_machine_finished(self, m: Machine, hand_item):

        self.start_robot_action(self.robot_action, m.name)

        target_slot = m.get_finished_slot()

        new_hand_item = {"type": target_slot.state, "attempt": target_slot.attempt, "from_m": m.name}

       

        target_slot.state = "PROCESSING"

        target_slot.timer = PROCESSING_TIME

        target_slot.attempt = hand_item["attempt"] + 1

       

        self.log(f"REWORK 交換 @ {m.name}: 放入 FAILED(a={target_slot.attempt}) <-> 換出 {new_hand_item['type']}")

        self.robot_hand = new_hand_item



    def put_into_machine_empty(self, m: Machine, hand_item):

        self.start_robot_action(self.robot_action, m.name)

        target_slot = m.get_empty_slot()

        target_slot.state = "PROCESSING"

        target_slot.timer = PROCESSING_TIME

        target_slot.attempt = hand_item["attempt"] + 1

       

        self.log(f"REWORK 填空 @ {m.name}: 放入 FAILED(a={target_slot.attempt}) 至 S{target_slot.slot_id}")

        self.robot_hand = None



    def step(self, delta_sec=1):

        self.sim_seconds += delta_sec

       

        arrived = 0

        remaining_transit = []

        for shipment in self.raw_in_transit:

            shipment["timer"] -= delta_sec

            if shipment["timer"] <= 0 and shipment["stage"] == "crane":

                shipment["stage"] = "conveyor"

                shipment["timer"] = CONVEYOR_TIME

                remaining_transit.append(shipment)

            elif shipment["timer"] <= 0:

                arrived += 1

            else:

                remaining_transit.append(shipment)

        self.raw_in_transit = remaining_transit

        self.raw_stock += arrived



        self.raw_gen_timer += delta_sec

        if self.raw_gen_timer >= RAW_GEN_INTERVAL:

            add_count = self.raw_gen_timer // RAW_GEN_INTERVAL

            self.raw_in_transit.extend([{"stage": "crane", "timer": RAW_TRANSPORT_TIME} for _ in range(add_count)])

            self.raw_gen_timer %= RAW_GEN_INTERVAL



        if self.robot_busy_timer > 0:

            self.robot_busy_timer -= delta_sec

            if self.robot_busy_timer < 0:

                self.robot_busy_timer = 0



        for m in self.machines:

            m.tick(delta_sec=delta_sec, failure_rate=self.failure_rate)



        self.robot_decision_cycle()



    def get_uph(self):

        hours = self.sim_seconds / 3600.0

        return self.good_sink / hours if hours > 0 else 0.0



# ---------------------------------------------------------

# GUI 介面繪製 (Tkinter)

# ---------------------------------------------------------

COLOR_MAP = {

    "EMPTY": "#343A46",

    "PROCESSING": "#2676C9",

    "GOOD": "#279768",

    "FAILED": "#D94F58",

}



class AppGUI:

    BG = "#171A21"

    PANEL = "#222733"

    MUTED = "#9AA4B2"

    TEXT = "#F1F4F8"



    def __init__(self, root, sim: FactorySim):

        self.root, self.sim = root, sim

        self.root.title("Factory Line | UPH Dashboard")

        self.root.geometry("1100x780")

        self.root.minsize(780, 600)

        self.root.configure(bg=self.BG)

        self.speed = 3000

        self.is_running = True

        self.selected_machine = 0

        self.setup_ui()

        self.update_loop()



    def setup_ui(self):

        top = tk.Frame(self.root, bg=self.PANEL, padx=16, pady=12)

        top.pack(fill="x", padx=12, pady=(12, 6))

        self.lbl_time = tk.Label(top, font=("Segoe UI", 11, "bold"), fg=self.TEXT, bg=self.PANEL)

        self.lbl_time.pack(side="left")

        self.lbl_uph = tk.Label(top, font=("Segoe UI", 19, "bold"), fg="#56D39B", bg=self.PANEL)

        self.lbl_uph.pack(side="left", padx=28)

        self.lbl_counters = tk.Label(top, font=("Segoe UI", 10), fg="#D4DAE3", bg=self.PANEL)

        self.lbl_counters.pack(side="right")



        robot = tk.Frame(self.root, bg="#2A303B", padx=14, pady=10)

        robot.pack(fill="x", padx=12, pady=6)

        self.lbl_robot_action = tk.Label(robot, font=("Segoe UI", 10, "bold"), fg="#FFD166", bg="#2A303B")

        self.lbl_robot_action.pack(side="left")

        self.lbl_robot_hand = tk.Label(robot, font=("Segoe UI", 10), fg=self.TEXT, bg="#2A303B")

        self.lbl_robot_hand.pack(side="right")



        controls = tk.Frame(self.root, bg=self.BG)

        controls.pack(fill="x", padx=16, pady=(2, 6))

        tk.Label(controls, text="模擬速度", fg=self.MUTED, bg=self.BG, font=("Segoe UI", 9)).pack(side="left")

        self.scale_speed = tk.Scale(controls, from_=10, to=20000, orient="horizontal", bg=self.BG,

                                    fg=self.TEXT, troughcolor="#343A46", highlightthickness=0, length=260)

        self.scale_speed.set(3000)

        self.scale_speed.pack(side="left", padx=8)

        tk.Label(controls, text="機台總覽 · 點選機台查看 slot", fg=self.MUTED, bg=self.BG,

                 font=("Segoe UI", 9)).pack(side="right")



        body = tk.Frame(self.root, bg=self.BG)

        body.pack(fill="both", expand=True, padx=12, pady=4)

        overview = tk.LabelFrame(body, text=" 機台 ", fg=self.TEXT, bg=self.BG,

                                 font=("Segoe UI", 10, "bold"), padx=6, pady=6)

        overview.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.machine_canvas = tk.Canvas(overview, bg=self.BG, highlightthickness=0)

        scrollbar = ttk.Scrollbar(overview, orient="vertical", command=self.machine_canvas.yview)

        self.machine_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")

        self.machine_canvas.pack(side="left", fill="both", expand=True)

        self.machine_list = tk.Frame(self.machine_canvas, bg=self.BG)

        self.machine_window = self.machine_canvas.create_window((0, 0), window=self.machine_list, anchor="nw")

        self.machine_list.bind("<Configure>", lambda _e: self.machine_canvas.configure(scrollregion=self.machine_canvas.bbox("all")))

        self.machine_canvas.bind("<Configure>", lambda e: self.machine_canvas.itemconfigure(self.machine_window, width=e.width))

        self.machine_canvas.bind_all("<MouseWheel>", self._scroll_machines)



        detail = tk.LabelFrame(body, text=" Slot 詳情 ", fg=self.TEXT, bg=self.BG,

                               font=("Segoe UI", 10, "bold"), padx=10, pady=8)

        detail.pack(side="right", fill="y", padx=(6, 0))

        self.detail_title = tk.Label(detail, fg="#56D39B", bg=self.BG, font=("Segoe UI", 12, "bold"), anchor="w")

        self.detail_title.pack(fill="x", pady=(2, 8))

        self.slot_widgets = {}

        self.detail_slots = tk.Frame(detail, bg=self.BG)

        self.detail_slots.pack(fill="both", expand=True)



        log_frame = tk.LabelFrame(self.root, text=" 動作紀錄 ", fg=self.TEXT, bg=self.BG)

        log_frame.pack(fill="x", padx=12, pady=(6, 12))

        self.log_box = tk.Text(log_frame, height=5, bg="#101319", fg="#A8E6C5", font=("Consolas", 9), state="disabled", relief="flat")

        self.log_box.pack(fill="both", padx=6, pady=6)



        self.machine_cards = []

        for idx, machine in enumerate(self.sim.machines):

            card = tk.Button(self.machine_list, anchor="w", justify="left", relief="flat",

                             command=lambda i=idx: self.select_machine(i), padx=10, pady=8,

                             font=("Segoe UI", 9), wraplength=450)

            card.pack(fill="x", pady=2)

            self.machine_cards.append(card)

        if self.sim.machines:

            self.select_machine(0)



    def _scroll_machines(self, event):

        if self.machine_canvas.winfo_containing(event.x_root, event.y_root):

            self.machine_canvas.yview_scroll(int(-event.delta / 120), "units")



    def select_machine(self, index):

        self.selected_machine = index

        machine = self.sim.machines[index]

        self.detail_title.config(text=f"{machine.name} · {len(machine.slots)} slots")

        for child in self.detail_slots.winfo_children():

            child.destroy()

        self.slot_widgets[machine.name] = []

        for idx, slot in enumerate(machine.slots):

            widget = tk.Label(self.detail_slots, width=18, height=2, relief="flat",

                              font=("Segoe UI", 9, "bold"), justify="left", padx=8)

            widget.grid(row=idx // 2, column=idx % 2, padx=3, pady=3, sticky="nsew")

            self.slot_widgets[machine.name].append(widget)

        for col in range(2):

            self.detail_slots.columnconfigure(col, weight=1)

        self.render()



    def _slot_text(self, slot):

        if slot.state == "PROCESSING":

            return f"S{slot.slot_id}   PROCESSING\n剩餘 {max(0, slot.timer) // 60} 分鐘"

        if slot.state in ("GOOD", "FAILED"):

            return f"S{slot.slot_id}   {slot.state}\n重試 {slot.attempt} 次"

        return f"S{slot.slot_id}   EMPTY"



    def render(self):

        hours, rem = divmod(self.sim.sim_seconds, 3600)

        minutes, seconds = divmod(rem, 60)

        self.lbl_time.config(text=f"模擬時間  {hours:02d}:{minutes:02d}:{seconds:02d}")

        self.lbl_uph.config(text=f"UPH  {self.sim.get_uph():.2f}")

        self.lbl_counters.config(text=f"Raw 可用 {self.sim.raw_stock}    天車/輸送帶運送中 {len(self.sim.raw_in_transit)}    GOOD {self.sim.good_sink}    SCRAP {self.sim.scrap_sink}")

        busy = f" ({self.sim.robot_busy_timer}s)" if self.sim.robot_busy_timer > 0 else ""

        self.lbl_robot_action.config(text=f"Robot  {self.sim.robot_action}{busy}")

        hand = "空" if self.sim.robot_hand is None else f"{self.sim.robot_hand['type']} · a={self.sim.robot_hand['attempt']} · {self.sim.robot_hand['from_m']}"

        self.lbl_robot_hand.config(text=f"手上物品  {hand}")



        for idx, machine in enumerate(self.sim.machines):

            counts = {state: sum(slot.state == state for slot in machine.slots)

                      for state in ("PROCESSING", "GOOD", "FAILED", "EMPTY")}

            self.machine_cards[idx].config(

                text=f"{machine.name:<6}  執行中 {counts['PROCESSING']}   完成 {counts['GOOD']}   異常 {counts['FAILED']}   空位 {counts['EMPTY']}",

                bg="#344457" if idx == self.selected_machine else self.PANEL, fg=self.TEXT,

                activebackground="#40536A", activeforeground=self.TEXT)



        machine = self.sim.machines[self.selected_machine]

        for slot, widget in zip(machine.slots, self.slot_widgets.get(machine.name, [])):

            widget.config(text=self._slot_text(slot), bg=COLOR_MAP[slot.state],

                          fg="#FFFFFF" if slot.state != "EMPTY" else "#C6CDD7")

        self.log_box.config(state="normal")

        self.log_box.delete("1.0", tk.END)

        self.log_box.insert(tk.END, "\n".join(self.sim.logs))

        self.log_box.see(tk.END)

        self.log_box.config(state="disabled")



    def update_loop(self):

        time_step = max(5, min(100, self.speed // 50))

        if self.is_running:

            self.speed = self.scale_speed.get()
            time_step = max(5, min(100, self.speed // 50))

            for _ in range(time_step):

                self.sim.step(delta_sec=1)

            self.render()

        delay_ms = max(1, int(time_step / max(1, self.speed) * 1000))

        self.root.after(delay_ms, self.update_loop)



def render_dashboard(sim):
    hours, remainder = divmod(sim.sim_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    metric_columns = st.columns(5)
    metric_columns[0].metric("模擬時間", f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    metric_columns[1].metric("UPH", f"{sim.get_uph():.2f}")
    metric_columns[2].metric("Raw 可用", sim.raw_stock)
    metric_columns[3].metric("GOOD", sim.good_sink)
    metric_columns[4].metric("SCRAP", sim.scrap_sink)

    transit_count = len(sim.raw_in_transit)
    busy = f" ({sim.robot_busy_timer}s)" if sim.robot_busy_timer > 0 else ""
    hand = "空" if sim.robot_hand is None else (
        f"{sim.robot_hand['type']} · a={sim.robot_hand['attempt']} · {sim.robot_hand['from_m']}"
    )
    st.info(
        f"Robot  {sim.robot_action}{busy}　|　手上物品 {hand}　|　"
        f"天車/輸送帶運送中 {transit_count}"
    )

    machines = []
    for machine in sim.machines:
        counts = {
            state: sum(slot.state == state for slot in machine.slots)
            for state in ("PROCESSING", "GOOD", "FAILED", "EMPTY")
        }
        machines.append({
            "機台": machine.name,
            "執行中": counts["PROCESSING"],
            "完成": counts["GOOD"],
            "異常": counts["FAILED"],
            "空位": counts["EMPTY"],
        })

    st.subheader("機台總覽")
    st.dataframe(machines, hide_index=True, use_container_width=True)

    machine_names = [machine.name for machine in sim.machines]
    selected_name = st.selectbox("查看機台 Slot", machine_names, key="selected_machine")
    selected_machine = next(machine for machine in sim.machines if machine.name == selected_name)
    slot_columns = st.columns(4)
    for index, slot in enumerate(selected_machine.slots):
        if slot.state == "PROCESSING":
            label = f"剩餘 {max(0, slot.timer) // 60} 分鐘"
        elif slot.state in ("GOOD", "FAILED"):
            label = f"重試 {slot.attempt} 次"
        else:
            label = "等待投入"
        with slot_columns[index % len(slot_columns)]:
            st.metric(f"S{slot.slot_id} · {slot.state}", label)

    st.subheader("動作紀錄")
    st.text("\n".join(reversed(sim.logs)) if sim.logs else "尚無紀錄")


def run_streamlit_app():
    st.set_page_config(page_title="Factory Line | UPH Dashboard", layout="wide")
    st.title("Factory Line | UPH Dashboard")

    if "sim_engine" not in st.session_state:
        st.session_state.sim_engine = FactorySim(
            num_machines=25, slots_per_machine=8, raw_stock=5, failure_rate=0.1
        )
        st.session_state.is_running = True

    control_columns = st.columns([2, 1, 1, 1])
    steps_per_update = control_columns[0].slider(
        "模擬速度（每次更新秒數）", min_value=5, max_value=1000, value=60, step=5
    )
    if control_columns[1].button(
        "暫停" if st.session_state.is_running else "繼續", use_container_width=True
    ):
        st.session_state.is_running = not st.session_state.is_running
    if control_columns[2].button("重設模擬", use_container_width=True):
        st.session_state.sim_engine = FactorySim(
            num_machines=25, slots_per_machine=8, raw_stock=5, failure_rate=0.1
        )
        st.session_state.is_running = True
    control_columns[3].caption("約每 0.2 秒更新一次")

    @st.fragment(run_every=0.2 if st.session_state.is_running else None)
    def simulation_view():
        sim = st.session_state.sim_engine
        if st.session_state.is_running:
            for _ in range(steps_per_update):
                sim.step()
        render_dashboard(sim)

    simulation_view()


if __name__ == "__main__":
    run_streamlit_app()
