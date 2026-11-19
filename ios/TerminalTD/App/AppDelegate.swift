import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let win = UIWindow(frame: UIScreen.main.bounds)
        win.backgroundColor = UIColor(red: 7/255, green: 13/255, blue: 20/255, alpha: 1)
        win.rootViewController = ViewController()
        win.makeKeyAndVisible()
        self.window = win
        return true
    }
}
