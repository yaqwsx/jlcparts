import React from 'react';
import {
  HashRouter as Router,
  Switch,
  Route,
  NavLink
} from "react-router-dom";


import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@fortawesome/free-solid-svg-icons'
import { far } from '@fortawesome/free-regular-svg-icons'
import { fab } from '@fortawesome/free-brands-svg-icons'

import './main.css';
import { updateComponentLibrary, checkForComponentLibraryUpdate, db, unpackLinesAsArray } from './db'
import { ComponentOverview } from './componentTable'
import { History } from './history'


library.add(fas, far, fab);

function Header(props) {
  return <>
    <div className="w-full px-2 py-8 flex">
      <img src="./favicon.svg" alt="" className="block flex-none mr-4 h-auto"/>
      <div className="flex-1">
        <h1 className="text-4xl font-bold">
          JLC PCB SMD Assembly Component Catalogue
        </h1>
        <p>
          Parametric search for components offered by <a href="https://jlcpcb.com/smt-assembly?from=JanMrazek" className="underline text-blue-600">JLC PCB SMD assembly service</a>.
        </p>
        <p>
          Read more at project's <a className="underline text-blue-500 hover:text-blue-800" href="https://github.com/yaqwsx/jlcparts">GitHub page</a>.
        </p>
      </div>
    </div>
    <div className="rounded my-3 p-2 border-blue-500 border-2">
      Do you enjoy this site? Consider supporting me so I can actively maintain projects like this one!
      Read more about <a className="underline text-blue-500 hover:text-blue-800" href="https://github.com/sponsors/yaqwsx">my story</a>.
      <table>
        <tbody>
          <tr>
            <td className="pr-2 text-right">
              GitHub Sponsors:
            </td>
            <td>
              <iframe src="https://github.com/sponsors/yaqwsx/button" title="Sponsor yaqwsx" height="35" width="116" style={{border: 0}} className="inline-block"></iframe>
            </td>
          </tr>
          <tr>
            <td className="pr-2 text-right">
              Ko-Fi:
            </td>
            <td>
              <a href="https://ko-fi.com/E1E2181LU">
                <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Ko-Fi button" className="inline-block"/>
              </a>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </>
}

function Footer(props) {
  return <div className="w-full p-2 border-t-2 border-gray-800" style={{minHeight: "200px"}}>

  </div>
}

class FirstTimeNote extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      componentCount: undefined
    };
  }

  componentDidMount() {
    unpackLinesAsArray('components').then(components => {
      this.setState({componentCount: Math.max(0, components.length - 1)});   // don't count the schema entry
    })
  }

  render() {
    if (this.state.componentCount === undefined || this.state.componentCount !== 0)
      return null;
    return <div className="w-full p-8 my-2 bg-yellow-400 rounded">
      <p>
        Hey, it seems that you run the application for the first time, hence,
        there's no component library in your device. Just press the "Update
        the component library button" in the upper right corner to download it
        and use the app.
      </p>
      <p>
        Note that the initial download of the component library might take a while.
      </p>
    </div>
  }
}

class NewComponentFormatWarning extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      newComponentFormat: true
    };
  }

  componentDidMount() {
    // I don't know if newComponentFormat will work like this
    unpackLinesAsArray('subcategories').then(cats => {
        if (cats.size > 1) {
            this.setState({newComponentFormat: false});
        }
    });
  }

  render() {
    if (this.state.newComponentFormat)
      return null;
    return <div className="w-full p-8 my-2 bg-yellow-400 rounded">
      <p>
        Hey, there have been some breaking changes to the library format.
        Please, update the library before continuing to use the tool.
      </p>
    </div>
  }
}

class UpdateBar extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      updateAvailable: this.props.updateAvailable
    };
  }

  componentDidMount() {
    let checkStatus = () => {
      checkForComponentLibraryUpdate().then( updateAvailable => {
        this.setState({updateAvailable});
      });
      db.settings.get("lastUpdate").then(lastUpdate => {
        this.setState({lastUpdate: lastUpdate?.value});
      })
    };

    checkStatus();
    this.timerID = setInterval(checkStatus, 60000);
  }

  componentWillUnmount() {
    clearInterval(this.timerID);
  }

  handleUpdateClick = e => {
    e.preventDefault();
    this.props.onTriggerUpdate();
  }

  render() {
    if (this.state.updateAvailable) {
      return <div className="flex flex-wrap w-full align-middle bg-yellow-400 p-2">
                <p className="inline-block w-full md:w-1/2 py-2">There is an update of the component library available.</p>
                <button className="inline-block w-full md:w-1/2 bg-green-500 hover:bg-green-600 py-2 px-4 rounded"
                        onClick={this.handleUpdateClick}>
                  Update the component library
                </button>
              </div>
    }
    else {
    return <div className="w-full bg-green-400 p-2 text-xs">
              <p>The component database is up to-date {this.state.lastUpdate ? `(${this.state.lastUpdate})` : ""}.</p>
            </div>
    }
  }
}

class Updater extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      progress: {}
    };
  }

  componentDidMount() {
    let t0 = performance.now();
    updateComponentLibrary(
      progress => { this.setState({progress}); }
    ).then(() => {
      let t1 = performance.now();
      console.log("Library update took ", t1 - t0, "ms");
      this.props.onFinish();
    });
  }

  listItems() {
    let items = []
    for (const [task, status] of Object.entries(this.state.progress)) {
      let color = status[1] ? "bg-green-500" : "bg-yellow-400";
      items.push(<tr key={task}>
        <td className="p-2">{task}</td>
        <td className={`p-2 ${color}`}>{status[0]}</td>
      </tr>)
    }
    return items;
  }

  render() {
    return <div className="w-full px-2 py-8">
      <h1 className="font-bold text-2xl">Update progress:</h1>
      <table className="w-full">
        <thead>
          <tr className="border-b-2 border-gray-800 font-bold">
            <td>Operation/category</td>
            <td>Progress</td>
          </tr>
        </thead>
        <tbody>
          {this.listItems()}
        </tbody>
      </table>
    </div>
  }
}

function Container(props) {
  return <div className="container mx-auto px-2">{props.children}</div>
}

function Navbar() {
  return <div className="w-ful text-lg">
    <NavLink to="/" exact={true}
      className="inline-block p-4 bg-white"
      activeClassName="bg-gray-200 font-bold">
      Component search
    </NavLink>
    <NavLink to="/history"
      className="inline-block p-4 bg-white"
      activeClassName="bg-gray-200 font-bold">
       Catalog history
    </NavLink>
  </div>
}

export function NoMatch() {
  return <p>404 not found</p>;
}

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      updating: false
    };
  }

  onUpdateFinish = () => {
    this.setState({updating: false});
  }

  triggerUpdate = () => {
    this.setState({updating: true});
  }

  render() {
    if (this.state.updating) {
      return <Container>
        <Updater onFinish={this.onUpdateFinish}/>
      </Container>
    }
    return (
      <Router basename="/" >
        <Container>
          <UpdateBar onTriggerUpdate={this.triggerUpdate}/>
          <Header/>
          <FirstTimeNote/>
          <NewComponentFormatWarning/>
          <Navbar/>
              <Switch>
                  <Route exact path="/">
                    <ComponentOverview/>
                  </Route>
                  <Route path="/history" component={History} />
                  <Route path="*">
                      <NoMatch />
                  </Route>
              </Switch>
          <Footer/>
        </Container>
      </Router>
    );
  }
}

export default App;
