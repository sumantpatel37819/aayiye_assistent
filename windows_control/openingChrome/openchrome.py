import pyautogui
import time

print("opening start")
time.sleep(3)
pyautogui.press('win')
print("presing the window button")

# searching button press karne ke liye for example chrome browser
pyautogui.typewrite('chrome', interval=0.1) 
time.sleep(1) 
pyautogui.press('enter')
print("chrome open ho gaya hai")

time.sleep(1)
pyautogui.click(x=1250, y=520) 
print("opening chrome browser")

#searching query of google browser
pyautogui.hotkey('ctrl', 't') 
time.sleep(1)
pyautogui.hotkey('tab', 'enter') 
time.sleep(0.5)
pyautogui.typewrite("give the result in propar json format, Mahaveer mandir patna opening time and entry fee, avg_time_spent, best_time_to_visit, others_name, description ", interval=0.1) 
time.sleep(1) 
pyautogui.press('enter')
print("query has been searched")